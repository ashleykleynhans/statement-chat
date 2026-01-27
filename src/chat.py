import json
import re
import time
from datetime import datetime, timedelta

from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .database import Database


class ChatInterface:
    """Interactive chat interface for querying bank transactions."""

    def __init__(
        self,
        db: Database,
        host: str = "localhost",
        port: int = 11434,
        model: str = "llama3.2"
    ):
        self.db = db
        self.model = model
        self._client = OpenAI(
            base_url=f"http://{host}:{port}/v1",
            api_key="lm-studio",  # LM Studio doesn't require a real key
            timeout=60.0,
        )
        self.console = Console()
        self._conversation_history = []
        self._last_transactions = []  # Store last query's transactions for follow-ups
        self._last_search_query = ""  # Store last search query for scope expansion
        self._last_llm_stats = None  # Store LLM performance stats

    def start(self) -> None:
        """Start the interactive chat loop."""
        self.console.print(Panel(
            "[bold green]BankBot[/bold green]\n\n"
            "Ask questions about your transactions, e.g.:\n"
            "- When did I last pay the doctor?\n"
            "- How much did I spend on groceries last month?\n"
            "- Show my largest expenses\n\n"
            "Type [bold]quit[/bold] or [bold]exit[/bold] to leave.",
            title="Welcome"
        ))

        stats = self.db.get_stats()
        self.console.print(
            f"[dim]Loaded {stats['total_transactions']} transactions "
            f"from {stats['total_statements']} statements[/dim]\n"
        )

        while True:
            try:
                user_input = self.console.input("[bold blue]You:[/bold blue] ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    self.console.print("[dim]Goodbye![/dim]")
                    break

                self._process_query(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[dim]Goodbye![/dim]")
                break
            except EOFError:
                break

    def _is_scope_expansion_request(self, query: str) -> bool:
        """Detect if user wants to expand search scope (e.g., 'check all history')."""
        query_lower = query.lower()
        expansion_patterns = [
            r"all\s+history",
            r"not\s+just\s+this\s+month",
            r"check\s+(?:all|everything)",
            r"search\s+(?:all|everything)",
            r"include\s+(?:all|everything)",
            r"across\s+all",
            r"all\s+time",
            r"entire\s+history",
        ]
        return any(re.search(p, query_lower) for p in expansion_patterns)

    def _process_query(self, query: str) -> None:
        """Process a user query and display the response."""
        # Check if user wants to expand search scope from previous query
        if self._is_scope_expansion_request(query) and self._last_search_query:
            # Re-search with previous query but force all history
            relevant_transactions = self._find_relevant_transactions(
                self._last_search_query, force_all_history=True
            )
            self._last_transactions = relevant_transactions
        # Check if this is a follow-up query about previous transactions
        elif self._is_follow_up_query(query) and self._last_transactions:
            relevant_transactions = self._last_transactions
        else:
            # Find new relevant transactions
            relevant_transactions = self._find_relevant_transactions(query)
            # Store for potential follow-up queries
            self._last_transactions = relevant_transactions
            self._last_search_query = query

        # Build context for the LLM
        context = self._build_context(relevant_transactions, query)

        # Get LLM response
        response = self._get_llm_response(query, context)

        self.console.print(f"\n[bold green]Assistant:[/bold green] {response}\n")

        # Show relevant transactions if found
        if relevant_transactions and len(relevant_transactions) <= 10:
            self._display_transactions(relevant_transactions)

    def _is_follow_up_query(self, query: str) -> bool:
        """Detect if query is a follow-up about previous transactions."""
        query_lower = query.lower()
        words = set(re.findall(r"\b\w+\b", query_lower))

        # Greetings are never follow-ups
        greetings = {"hi", "hello", "hey", "howdy", "greetings", "thanks"}
        if words & greetings:
            return False

        # Pronouns/references that indicate follow-up
        follow_up_indicators = {
            "them", "these", "those", "it", "they",
            "above", "previous",
            "group", "sort", "filter", "summarize",
            "sum", "average", "breakdown", "analyze"
        }

        # Check for follow-up indicators (word-based match)
        if words & follow_up_indicators:
            return True

        # If query has no specific transaction keywords, might be follow-up
        has_specific_keywords = any(word in query_lower for word in [
            "show", "find", "search", "list", "electricity", "groceries", "fuel",
            "medical", "salary", "deposit", "last month", "this month",
            "budget", "saved", "savings", "spent", "spend", "remaining"
        ])

        # "Did I pay X?" or "Pay X" patterns with a name are specific queries
        if re.search(r"\bpay\s+[A-Z][a-z]+", query) or re.search(r"\bpaid\s+[A-Z][a-z]+", query):
            has_specific_keywords = True

        # Proper nouns (capitalized names like "Chanel Smith" or "Netflix") are specific queries
        # Find all capitalized words and filter out common sentence starters
        common_starters = {
            "show", "list", "find", "when", "what", "how", "did", "have", "where",
            "who", "why", "is", "are", "can", "the", "a", "an", "i", "my", "hi",
            "hello", "hey", "please", "could", "would", "tell", "give", "get",
        }
        capitalized_words = re.findall(r'\b[A-Z][a-z]+\b', query)
        proper_nouns = [w for w in capitalized_words if w.lower() not in common_starters]
        if proper_nouns:
            has_specific_keywords = True

        # Check if query mentions any category name
        if not has_specific_keywords:
            categories = self.db.get_all_categories()
            for category in categories:
                if category and category.lower().replace("_", " ") in query_lower:
                    has_specific_keywords = True
                    break

        # Short queries without specific keywords are likely follow-ups
        if len(query.split()) <= 5 and not has_specific_keywords:
            return True

        return False

    def _find_relevant_transactions(
        self, query: str, force_all_history: bool = False
    ) -> list[dict]:
        """Find transactions relevant to the user's query."""
        query_lower = query.lower()

        # Check if user is asking for the most recent one only
        is_when_last = "when last" in query_lower or "last time" in query_lower

        def limit_if_when_last(transactions: list[dict]) -> list[dict]:
            """For 'when last' queries, return only the most recent transaction."""
            if is_when_last and transactions:
                sorted_txs = sorted(transactions, key=lambda x: x.get("date", ""), reverse=True)
                return sorted_txs[:1]
            return transactions

        # Don't return transactions for greetings
        words = set(query_lower.split())
        is_greeting = (words & {"hi", "hello", "hey", "howdy", "greetings", "thanks"} or
                       any(g in query_lower for g in ["good morning", "good afternoon", "good evening", "thank you"]))
        if is_greeting and len(query.split()) <= 5:
            return []

        # First, determine date range if specified (skip if forcing all history)
        date_start = None
        date_end = None

        if not force_all_history:
            if "last month" in query_lower:
                today = datetime.now()
                date_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
                date_end = today.replace(day=1) - timedelta(days=1)
            elif "this month" in query_lower:
                today = datetime.now()
                date_start = today.replace(day=1)
                date_end = today

        # Special handling for "doctor" queries - search descriptions, not category
        # This avoids returning medical aid/insurance when user asks about doctor visits
        if "doctor" in query_lower or "doctors" in query_lower:
            # Search for actual doctor visits, not medical aid
            doctor_terms = ["dr ", "doctor", "cardiologist", "neurologist", "dentist",
                           "optom", "medicross", "mediclinic", "netcare", "hospital"]
            exclude_terms = ["med aid", "medihelp", "health ins", "tms health"]

            all_medical = self.db.get_transactions_by_category("medical")
            doctor_transactions = []
            for tx in all_medical:
                desc_lower = tx.get("description", "").lower()
                # Include if it matches doctor terms
                if any(term in desc_lower for term in doctor_terms):
                    # But exclude if it's medical aid/insurance
                    if not any(excl in desc_lower for excl in exclude_terms):
                        doctor_transactions.append(tx)
            return limit_if_when_last(doctor_transactions)

        # Check for category keywords (with common synonyms)
        # These synonyms map to a category but should also filter by description
        category_synonyms = {
            "saved": "savings",
            "save": "savings",
            "petrol": "fuel",
            "gas": "fuel",
            "medical aid": "medical",  # Only map "medical aid" to category, not "doctor"
            "flowers": "florist",
            "flower": "florist",
        }
        # These synonyms map to a category but need description filtering
        # (multiple things map to same category, e.g., roof/ceiling/pool → home_maintenance)
        description_filter_synonyms = {
            "roof": "home_maintenance",
            "ceiling": "home_maintenance",
            "electrician": "home_maintenance",
            "plumber": "home_maintenance",
            "garage": "home_maintenance",
            "pool": "home_maintenance",
            "fence": "home_maintenance",
        }

        # Track if we need to filter by description term
        description_filter_term = None
        for synonym, category in description_filter_synonyms.items():
            if synonym in query_lower:
                description_filter_term = synonym
                break

        # Expand query with synonyms
        expanded_query = query_lower
        for synonym, category in category_synonyms.items():
            if synonym in query_lower:
                expanded_query += f" {category}"
        for synonym, category in description_filter_synonyms.items():
            if synonym in query_lower:
                expanded_query += f" {category}"

        categories = self.db.get_all_categories()
        matched_category = None
        for category in categories:
            if category and category.lower() in expanded_query:
                matched_category = category
                break

        # If query is about budget, filter to latest statement only
        is_budget_query = "budget" in query_lower
        if is_budget_query:
            latest_stmt = self.db.get_latest_statement()
            if latest_stmt and latest_stmt.get("statement_number"):
                stmt_num = latest_stmt["statement_number"]
                if matched_category:
                    # Specific category budget - show those transactions
                    stmt_transactions = self.db.get_transactions_by_statement(stmt_num)
                    return [tx for tx in stmt_transactions if tx.get("category") == matched_category]
                # General budget question - don't show transactions
                return []

        # Helper to filter by description term if needed
        def filter_by_description(transactions):
            if description_filter_term:
                return [tx for tx in transactions
                        if description_filter_term in tx.get("description", "").lower()]
            return transactions

        # If we have both date range and category, filter by both
        if date_start and date_end and matched_category:
            all_in_range = self.db.get_transactions_in_date_range(
                date_start.strftime("%Y-%m-%d"),
                date_end.strftime("%Y-%m-%d")
            )
            filtered = [tx for tx in all_in_range if tx.get("category") == matched_category]
            return limit_if_when_last(filter_by_description(filtered))

        # If only category specified
        if matched_category:
            transactions = self.db.get_transactions_by_category(matched_category)
            return limit_if_when_last(filter_by_description(transactions))

        # If only date range specified
        if date_start and date_end:
            results = self.db.get_transactions_in_date_range(
                date_start.strftime("%Y-%m-%d"),
                date_end.strftime("%Y-%m-%d")
            )
            return limit_if_when_last(results)

        # Check for transaction type
        if "credit" in query_lower or "deposit" in query_lower or "income" in query_lower:
            return limit_if_when_last(self.db.get_transactions_by_type("credit"))
        if "debit" in query_lower or "expense" in query_lower or "payment" in query_lower:
            # Don't return all debits, too many - let search narrow it down
            pass

        # Detect proper nouns (person/business names like "Chanel Smith")
        # and search for the full name as a phrase first, before LLM extraction
        common_starters = {
            "show", "list", "find", "when", "what", "how", "did", "have", "where",
            "who", "why", "is", "are", "can", "the", "a", "an", "i", "my", "hi",
            "hello", "hey", "please", "could", "would", "tell", "give", "get",
            "do", "does", "has", "was", "were", "all",
        }
        capitalized_words = re.findall(r'\b[A-Z][a-z]+\b', query)
        proper_nouns = [w for w in capitalized_words if w.lower() not in common_starters]
        if len(proper_nouns) >= 2:
            # Search for the full proper noun phrase (e.g., "Chanel Smith")
            full_name = " ".join(proper_nouns).lower()
            results = self.db.search_transactions(full_name)
            if results:
                filtered = [tx for tx in results if tx.get("category") != "fees"]
                if filtered:
                    return limit_if_when_last(filtered)
        elif len(proper_nouns) == 1:
            # Single proper noun (e.g., "Netflix", "Spotify")
            results = self.db.search_transactions(proper_nouns[0].lower())
            if results:
                filtered = [tx for tx in results if tx.get("category") != "fees"]
                if filtered:
                    return limit_if_when_last(filtered)

        # Helper to filter out fee transactions (unless specifically searching for fees)
        def filter_fees(results: list[dict], query: str) -> list[dict]:
            if "fee" in query.lower():
                return results  # Keep fees if user asked about fees
            return [tx for tx in results if tx.get("category") != "fees"]

        def _search_with_terms(search_terms: list[str]) -> list[dict] | None:
            """Try searching DB with given terms. Returns results or None."""
            # First try multi-word phrases (e.g., "ceiling repairs" not just "ceiling")
            if len(search_terms) >= 2:
                for i in range(len(search_terms) - 1):
                    phrase = f"{search_terms[i]} {search_terms[i+1]}"
                    results = self.db.search_transactions(phrase)
                    if results:
                        filtered = filter_fees(results, query)
                        if filtered:
                            return limit_if_when_last(filtered)

            # Fall back to individual terms
            for term in search_terms:
                results = self.db.search_transactions(term)
                if results:
                    filtered = filter_fees(results, query)
                    if filtered:
                        return limit_if_when_last(filtered)
                # Try hyphen variations (xray <-> x-ray, e-mail <-> email)
                variations = []
                if "-" in term:
                    variations.append(term.replace("-", ""))
                else:
                    for prefix in ["x", "e", "t", "re", "pre"]:
                        if term.startswith(prefix) and len(term) > len(prefix):
                            variations.append(prefix + "-" + term[len(prefix):])
                for variant in variations:
                    results = self.db.search_transactions(variant)
                    if results:
                        filtered = filter_fees(results, query)
                        if filtered:
                            return limit_if_when_last(filtered)
            return None

        # Try simple extraction first (no LLM call) — fast path
        stop_words = {
            "when", "did", "i", "the", "a", "an", "to", "for", "of", "in",
            "my", "me", "last", "first", "how", "much", "many", "what",
            "where", "why", "show", "find", "get", "list", "all", "pay",
            "paid", "spend", "spent", "make", "made", "payment", "payments",
            "send", "sent", "transfer", "transferred", "buy", "bought",
            "transactions", "transaction",
        }
        simple_terms = re.findall(r"\b[a-zA-Z]+(?:-[a-zA-Z]+)*\b", query_lower)
        simple_terms = [w for w in simple_terms if w not in stop_words and len(w) > 2]

        if simple_terms:
            result = _search_with_terms(simple_terms)
            if result is not None:
                return result

        # Simple terms found nothing — try LLM for typo correction
        llm_terms = self._extract_search_terms(query)
        if llm_terms != simple_terms:
            result = _search_with_terms(llm_terms)
            if result is not None:
                return result

        # Only fall back to recent transactions for purely vague queries
        # Check if query only contains vague/generic words
        vague_words = {"recent", "latest", "transactions", "transaction", "all", "my", "show", "list", "get"}
        query_words = set(re.findall(r"\b\w+\b", query_lower))
        is_purely_vague = query_words.issubset(vague_words)

        if is_purely_vague:
            return self.db.get_all_transactions(limit=20)

        # No matches found for specific query - return empty
        return []

    def _extract_search_terms(self, query: str) -> list[str]:
        """Extract and correct search terms from query using LLM."""
        query_lower = query.lower()

        # First, do simple extraction to get terms from the actual query
        stop_words = {
            "when", "did", "i", "the", "a", "an", "to", "for", "of", "in",
            "my", "me", "last", "first", "how", "much", "many", "what",
            "where", "why", "show", "find", "get", "list", "all", "pay",
            "paid", "spend", "spent", "make", "made", "payment", "payments",
            "send", "sent", "transfer", "transferred", "buy", "bought",
        }
        simple_terms = re.findall(r"\b[a-zA-Z]+(?:-[a-zA-Z]+)*\b", query_lower)
        simple_terms = [w for w in simple_terms if w not in stop_words and len(w) > 2]

        # Try LLM for typo correction only
        try:
            response = self._client.with_options(timeout=15.0).chat.completions.create(
                model=self.model,
                messages=[{
                    "role": "user",
                    "content": f"""In this query, what merchant/company/store is the user asking about? If misspelled, correct it.
Answer with ONLY the name, nothing else. If you cannot determine the merchant, reply with "unknown".

Query: {query}"""
                }],
                temperature=0
            )
            terms_text = response.choices[0].message.content.strip().lower()

            # Reject if LLM says unknown or returns something not in the query
            if terms_text and terms_text != "unknown":
                # Handle "X -> Y" format (e.g., "Metaflix -> Netflix")
                # This indicates explicit correction, so trust the right side
                if "->" in terms_text:
                    right_side = terms_text.split("->")[-1].strip()
                    right_words = re.findall(r'\b[a-z]+\b', right_side)
                    if right_words:
                        return [right_words[0]]

                # Validate: the LLM term must actually appear in the original query
                # or be a very close typo correction (edit distance <= 2)
                llm_words = re.findall(r'\b[a-z]+\b', terms_text)

                # If LLM returned a multi-word name (e.g., "chanel smith"),
                # check if the full phrase appears in the query first
                if len(llm_words) >= 2:
                    full_name = " ".join(w for w in llm_words if len(w) >= 3)
                    if full_name and full_name in query_lower:
                        return [full_name]

                for llm_word in llm_words:
                    if len(llm_word) < 3:
                        continue
                    # Check if LLM term appears in original query (substring match)
                    if llm_word in query_lower:
                        return [llm_word]
                    # Check for typo correction: term must be very similar to a query word
                    for query_word in simple_terms:
                        # Very close typo (e.g., sportify -> spotify): similar length, differ by 1-2 chars
                        len_diff = abs(len(llm_word) - len(query_word))
                        if len_diff <= 1:
                            # Compare character by character, accounting for inserted/deleted char
                            shorter, longer = (llm_word, query_word) if len(llm_word) <= len(query_word) else (query_word, llm_word)
                            # Simple diff count for same length
                            if len_diff == 0:
                                diffs = sum(1 for a, b in zip(llm_word, query_word) if a != b)
                            else:
                                # For length diff of 1, check if removing one char makes them match
                                diffs = len(longer)  # Start with max diff
                                for i in range(len(longer)):
                                    # Try removing char at position i from longer string
                                    modified = longer[:i] + longer[i+1:]
                                    diffs = min(diffs, sum(1 for a, b in zip(shorter, modified) if a != b))
                            if diffs <= 2:
                                return [llm_word]
        except Exception:
            pass  # Fall back to simple extraction

        # Return simple extraction from the original query
        return simple_terms

    def _detect_price_change(self, transactions: list[dict]) -> str | None:
        """Detect price changes in recurring transactions (e.g., subscriptions)."""
        if not transactions or len(transactions) < 2:
            return None

        # Filter out fee transactions - they're not the actual subscription price
        non_fee_txs = [tx for tx in transactions if tx.get("category") != "fees"]
        if len(non_fee_txs) < 2:
            return None

        # Sort by date
        sorted_txs = sorted(non_fee_txs, key=lambda x: x.get("date", ""))

        # Group by month and get the typical amount per month (first transaction)
        # This handles cases where there might be multiple charges in a month
        monthly_amounts = {}
        for tx in sorted_txs:
            month = tx.get("date", "")[:7]
            # Use abs() in case debits are stored as negative values
            amount = round(abs(float(tx.get("amount", 0))), 2)
            if month and month not in monthly_amounts:
                monthly_amounts[month] = amount

        if len(monthly_amounts) < 2:
            return None

        # Sort months chronologically and find where amount changed
        sorted_months = sorted(monthly_amounts.keys())
        prev_month = None
        prev_amount = None

        for month in sorted_months:
            amount = monthly_amounts[month]
            if prev_amount is not None and abs(amount - prev_amount) > 0.01:
                # Convert YYYY-MM to human readable format (e.g., "September 2025")
                from datetime import datetime
                month_date = datetime.strptime(month, "%Y-%m")
                month_name = month_date.strftime("%B %Y")
                # Found a change - determine if increase or decrease
                if amount > prev_amount:
                    return f"PRICE INCREASED in {month_name} from R{prev_amount:.2f} to R{amount:.2f}"
                else:
                    return f"PRICE DECREASED in {month_name} from R{prev_amount:.2f} to R{amount:.2f}"
            prev_month = month
            prev_amount = amount

        return None

    def _build_context(self, transactions: list[dict], query: str) -> str:
        """Build context string for LLM from transactions."""
        stats = self.db.get_stats()
        query_lower = query.lower()
        is_budget_query = "budget" in query_lower
        # Skip totals for "when last" type queries - they only want the most recent
        is_when_last_query = "when last" in query_lower or "last time" in query_lower
        is_price_change_query = "price" in query_lower and ("increase" in query_lower or "change" in query_lower or "go up" in query_lower)

        # For non-budget queries with no transactions, return early
        if not transactions and not is_budget_query:
            return "No matching transactions found in the database."

        context_parts = [
            f"Database contains {stats['total_transactions']} transactions.",
        ]

        if transactions:
            # Extract the dominant merchant/entity from transactions to anchor the LLM
            merchant = self._extract_merchant_name(transactions)
            if merchant and merchant != "this service":
                context_parts.append(f"Found {len(transactions)} transactions for {merchant}.")
            else:
                context_parts.append(f"Found {len(transactions)} potentially relevant transactions.")

        # For price change queries, detect and include the answer
        if is_price_change_query and transactions:
            price_change = self._detect_price_change(transactions)
            if price_change:
                context_parts.append(f"\n>>> {price_change} <<<")
            else:
                context_parts.append("\n>>> NO PRICE CHANGE DETECTED - amount stayed the same <<<")

        # If query is about budget, include budget info
        if is_budget_query:
            budgets = self.db.get_all_budgets()
            latest_stmt = self.db.get_latest_statement()
            budget_categories = {b["category"] for b in budgets}

            # Check if the user asked about a specific category that has no budget
            categories = self.db.get_all_categories()
            asked_category = None
            for category in categories:
                if category and category.lower().replace("_", " ") in query_lower:
                    asked_category = category
                    break
            if asked_category and asked_category not in budget_categories:
                context_parts.append(
                    f"\n>>> NO BUDGET SET for {asked_category}. "
                    f"The user has NOT set a budget for this category. <<<"
                )

            if budgets and latest_stmt:
                stmt_num = latest_stmt.get("statement_number")
                stmt_date = latest_stmt.get("statement_date", "")
                context_parts.append(f"\nLatest statement: #{stmt_num} ({stmt_date})")
                context_parts.append("\nBudget status for latest statement:")

                # Get category summary for latest statement only
                if stmt_num:
                    category_summary = self.db.get_category_summary_for_statement(stmt_num)
                    actual_by_cat = {s["category"]: abs(s.get("total_debits", 0) or 0) for s in category_summary}

                    total_budgeted = 0.0
                    total_spent = 0.0
                    for budget in budgets:
                        cat = budget["category"]
                        budget_amt = budget["amount"]
                        actual = actual_by_cat.get(cat, 0)
                        remaining = budget_amt - actual
                        pct = (actual / budget_amt * 100) if budget_amt > 0 else 0
                        status = "OVER BUDGET" if pct > 100 else f"{pct:.0f}% used"
                        total_budgeted += budget_amt
                        total_spent += actual
                        context_parts.append(
                            f"- {cat}: R{actual:,.2f} spent of R{budget_amt:,.2f} budget "
                            f"(R{remaining:,.2f} remaining, {status})"
                        )

                    total_remaining = total_budgeted - total_spent
                    context_parts.append(
                        f"\n>>> OVERALL BUDGET TOTAL: R{total_budgeted:,.2f} budgeted, "
                        f"R{total_spent:,.2f} spent, R{total_remaining:,.2f} remaining <<<"
                    )

        # Only include transactions section if there are transactions
        if transactions:
            # Sort by date (newest first) for display
            sorted_txs = sorted(transactions, key=lambda x: x.get("date", ""), reverse=True)

            # Count debits and credits
            debit_count = sum(1 for tx in sorted_txs[:15] if tx.get("transaction_type") == "debit")
            credit_count = sum(1 for tx in sorted_txs[:15] if tx.get("transaction_type") == "credit")

            context_parts.append(f"\n{len(sorted_txs[:15])} transactions ({debit_count} payments, {credit_count} deposits):")

            # Limit to most relevant transactions for context
            total_debits = 0.0
            total_credits = 0.0
            for tx in sorted_txs[:15]:
                date = tx.get("date", "Unknown")
                desc = tx.get("description", "")[:50]
                amount = tx.get("amount", 0)
                category = tx.get("category", "uncategorized")
                tx_type = tx.get("transaction_type", "unknown")
                recipient = tx.get("recipient_or_payer", "")

                if tx_type == "debit":
                    total_debits += abs(amount)
                else:
                    total_credits += abs(amount)

                line = f"- {date}: {desc}"
                if recipient:
                    line += f" ({recipient})"
                line += f" | R{abs(amount):,.2f} {tx_type} | {category}"
                context_parts.append(line)

            if len(sorted_txs) > 15:
                context_parts.append(f"\n... and {len(transactions) - 15} more transactions")

            # Provide pre-calculated totals - but skip for "when last" queries
            if not is_when_last_query:
                context_parts.append(f"\n>>> {debit_count} PAYMENTS TOTALING: R{total_debits:,.2f} | {credit_count} DEPOSITS TOTALING: R{total_credits:,.2f} <<<")

        return "\n".join(context_parts)

    def _get_llm_response(self, query: str, context: str) -> str:
        """Get response from LLM."""
        today = datetime.now()
        current_date = today.strftime("%Y-%m-%d")
        current_month = today.strftime("%B %Y")
        last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%B %Y")

        system_prompt = f"""You are a helpful assistant that answers questions about bank transactions.
Be concise and direct. Use South African Rand (R) for amounts.
Always address the user as "you"/"your", never "the user".

For greetings (hi, hello, hey, etc.), respond with a friendly greeting and offer to help with their transactions. Don't list transaction data for greetings.

When answering questions about spending or transactions:
- Give a concise summary with the total amount
- For yes/no questions like "Did I pay X?" or "Have I paid X?", start with yes/no then include the date and amount: "Yes, you paid Paul R500.00 on 15 January 2025."
- For "when" questions like "When last did I pay X?" or "When did I pay X?", answer with the date directly: "You last paid Paul R500.00 on 15 January 2025." Do NOT start with "Yes".
- Always format dates as "15 January 2025" (day month year), NEVER as "2025-01-15"
- For single transactions, always mention the date and amount
- If the context contains transactions, ALWAYS report on them - the user may have misspelled the name
- CRITICAL: Use the merchant name from the ACTUAL TRANSACTIONS in context (e.g. "Netflix"), NEVER the user's misspelling (e.g. "Metaflix")
- NEVER say "no payments found" if the context shows transactions - those ARE the relevant results
- The context shows ">>> X PAYMENTS TOTALING: R27,030.98 <<<" - COPY this amount EXACTLY including the cents
- NEVER round! R27,030.98 must stay R27,030.98, NOT R27,031.00
- NEVER do your own math - just copy the total from context
- For medical/doctor transactions: say "the doctor", not names from payment references
- If user says "list", give a summary like "10 payments to Chanel Smith totaling R14,206.20" - do NOT list individual transactions (they can click "Show transactions")
- NEVER use (x2), (x3), "twice", etc - NEVER combine multiple amounts on one line
- When a transaction has a reference number or code (e.g. "Sw4255", "10391 Kleynhans"), put it in brackets after the description: "Roof Repairs (Sw4255)", "Ceiling Repairs (10391 Kleynhans)"

For price change/increase questions:
- Context will contain ">>> PRICE INCREASED in [Month Year] from R[amount] to R[amount] <<<"
- Example: ">>> PRICE INCREASED in September 2025 from R99.99 to R119.99 <<<"
- Response: "Your Spotify price increased in September 2025 from R99.99 to R119.99."
- Use the merchant name from the transactions (e.g. "Netflix"), NOT the user's query (e.g. "Metaflix")
- COPY the month name exactly (e.g. "September 2025") - do NOT convert to a date like "2025-09-29"
- If context says "NO PRICE CHANGE DETECTED", respond that the price stayed the same

For budget questions:
- If asked about a SPECIFIC category (e.g. "medical budget", "groceries budget"):
  - Find THAT category's line: "- medical: R8,615.00 spent of R8,000.00 budget (R-615.00 remaining, OVER BUDGET)"
  - Response: "Your medical budget is R8,000.00. You've spent R8,615.00 (108% used). You are OVER BUDGET by R615.00."
  - If that category is NOT listed in the budget status, say: "You haven't set a budget for groceries yet. Say 'Set my groceries budget to R5000' to create one."
  - DO NOT use the overall budget numbers for category questions!
- If asked about OVERALL/TOTAL budget or just "budget remaining" without a category:
  - Find ">>> OVERALL BUDGET TOTAL: R29,060.00 budgeted, R28,127.90 spent, R932.10 remaining <<<"
  - Response: "Your overall budget is R29,060.00. You've spent R28,127.90 (97% used), with R932.10 remaining."
- ALWAYS include: budget amount, spent amount, percentage, and remaining/over status
- YOUR MATH IS WRONG - NEVER calculate - just COPY the exact numbers from context
- NEVER give short answers - always use the full format above

"Saved" or "savings" refers to transactions in the "savings" category (transfers to savings/investments), not credits received.

Today is {current_date}. Current month: {current_month}. Last month: {last_month}."""

        user_message = f"""Context:
{context}

Question: {query}

Answer concisely and directly."""

        # Store only the short query in history (not full context) to keep
        # the conversation history compact for local LLMs.  The full context
        # with transaction data is only attached to the *current* message.
        self._conversation_history.append({
            "role": "user",
            "content": query
        })

        try:
            # Build messages with system prompt and conversation history
            # Limit history to last 10 messages (5 exchanges) to prevent
            # local LLMs from getting confused by older, unrelated queries
            messages = [{"role": "system", "content": system_prompt}]
            recent_history = self._conversation_history[-10:]
            # Ensure history starts with a user message so roles
            # alternate correctly (system → user → assistant → …).
            # Slicing can land on an assistant message mid-conversation.
            while recent_history and recent_history[0]["role"] != "user":
                recent_history = recent_history[1:]
            # Add prior history (without the current query which is last)
            messages.extend(recent_history[:-1])
            # Add current query with full context
            messages.append({"role": "user", "content": user_message})

            start_time = time.time()
            response = self._client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3
            )
            elapsed_time = time.time() - start_time

            assistant_response = response.choices[0].message.content.strip()
            # Strip model reasoning/thinking tags and box formatting markers
            assistant_response = re.sub(r'<think>.*?</think>\s*', '', assistant_response, flags=re.DOTALL)
            assistant_response = re.sub(r'<\|begin_of_box\|>|<\|end_of_box\|>', '', assistant_response)
            assistant_response = assistant_response.strip()

            # Extract token usage if available
            usage = getattr(response, 'usage', None)
            if usage:
                completion_tokens = getattr(usage, 'completion_tokens', 0)
                prompt_tokens = getattr(usage, 'prompt_tokens', 0)
                total_tokens = getattr(usage, 'total_tokens', 0)
            else:
                # Estimate tokens (~4 chars per token)
                completion_tokens = len(assistant_response) // 4
                prompt_tokens = sum(len(m.get('content', '')) for m in messages) // 4
                total_tokens = completion_tokens + prompt_tokens

            # Calculate tokens per second (completion tokens / time)
            tokens_per_second = completion_tokens / elapsed_time if elapsed_time > 0 else 0

            # Store stats for retrieval
            self._last_llm_stats = {
                'completion_tokens': completion_tokens,
                'prompt_tokens': prompt_tokens,
                'total_tokens': total_tokens,
                'elapsed_time': round(elapsed_time, 2),
                'tokens_per_second': round(tokens_per_second, 1),
            }

            # Add assistant response to history
            self._conversation_history.append({
                "role": "assistant",
                "content": assistant_response
            })

            return assistant_response
        except Exception as e:
            # Remove the failed user message from history
            self._conversation_history.pop()
            self._last_llm_stats = None
            return f"Sorry, I couldn't process your request. Error: {str(e)}"

    def _display_transactions(self, transactions: list[dict]) -> None:
        """Display transactions in a formatted table."""
        table = Table(title="Matching Transactions", show_lines=True)
        table.add_column("Date", style="cyan")
        table.add_column("Description", style="white")
        table.add_column("Amount", justify="right")
        table.add_column("Category", style="magenta")

        for tx in transactions[:10]:
            date = tx.get("date", "")
            desc = tx.get("description", "")[:40]
            amount = tx.get("amount", 0)
            category = tx.get("category", "")
            tx_type = tx.get("transaction_type", "")

            amount_str = f"R{abs(amount):.2f}"
            if tx_type == "debit":
                amount_str = f"[red]-{amount_str}[/red]"
            else:
                amount_str = f"[green]+{amount_str}[/green]"

            table.add_row(date, desc, amount_str, category or "-")

        self.console.print(table)
        self.console.print()

    def _handle_budget_update(self, query: str) -> str | None:
        """Check if query is a budget update or delete request and handle it."""
        query_lower = query.lower()

        # Check for budget delete patterns first
        delete_patterns = [
            r"(?:delete|remove|clear)\s+(?:my\s+)?(\w+)\s+budget",
            r"(?:delete|remove|clear)\s+(?:the\s+)?budget\s+(?:for|of)\s+(\w+)",
        ]

        for pattern in delete_patterns:
            match = re.search(pattern, query_lower)
            if match:
                category = match.group(1).strip()

                # Verify category exists
                valid_categories = self.db.get_all_categories()
                if category not in [c.lower() for c in valid_categories if c]:
                    return f"'{category}' is not a valid category."

                # Delete the budget
                if self.db.delete_budget(category):
                    return f"Budget for {category} has been deleted."
                else:
                    return f"No budget found for {category}."

        # Check for budget update patterns
        budget_patterns = [
            r"(?:add|set|update|change)\s+(?:my\s+)?(\w+)\s+budget\s+to\s+r?([\d,]+(?:\.\d{2})?)",
            r"(?:add|set|update|change)\s+r?([\d,]+(?:\.\d{2})?)\s+(?:for|to)\s+(?:my\s+)?(\w+)\s+budget",
            r"(?:add|set)\s+r?([\d,]+(?:\.\d{2})?)\s+(?:for|to)\s+(\w+)",
        ]

        for pattern in budget_patterns:
            match = re.search(pattern, query_lower)
            if match:
                groups = match.groups()
                # Determine which group is category and which is amount
                if groups[0].replace(",", "").replace(".", "").isdigit():
                    amount_str, category = groups[0], groups[1]
                else:
                    category, amount_str = groups[0], groups[1]

                # Clean and validate
                amount = float(amount_str.replace(",", ""))
                category = category.strip()

                # Verify category exists
                valid_categories = self.db.get_all_categories()
                if category not in [c.lower() for c in valid_categories if c]:
                    return f"'{category}' is not a valid category. Valid categories include: {', '.join(sorted(c for c in valid_categories if c)[:10])}..."

                # Update the budget
                self.db.upsert_budget(category, amount)

                # Get current spending for this category to show progress
                latest_stmt = self.db.get_latest_statement()
                spent = 0.0
                if latest_stmt and latest_stmt.get("statement_number"):
                    category_summary = self.db.get_category_summary_for_statement(
                        latest_stmt["statement_number"]
                    )
                    for summary in category_summary:
                        if summary.get("category", "").lower() == category:
                            spent = abs(summary.get("total_debits", 0) or 0)
                            break

                percent = int((spent / amount * 100)) if amount > 0 else 0
                return f"Budget updated! Your {category} budget is R{amount:,.2f}. You've spent R{spent:,.2f} ({percent}% used)."

        return None

    def _extract_merchant_name(self, transactions: list[dict]) -> str:
        """Extract a clean merchant name from transactions."""
        if not transactions:
            return "this service"
        # Get the first transaction's description and extract merchant name
        desc = transactions[0].get("description", "")
        # Common patterns: "POS Purchase Netflix.Com", "Spotify Premium", etc.
        # Try to extract the key part
        desc_lower = desc.lower()
        for keyword in ["netflix", "spotify", "youtube", "apple", "google", "amazon", "disney"]:
            if keyword in desc_lower:
                return keyword.capitalize()
        # Fall back to first meaningful word
        words = desc.split()
        for word in words:
            if len(word) > 3 and word.lower() not in ["purchase", "payment", "pos", "debit"]:
                return word.strip(".,")
        return "this service"

    def ask(self, query: str) -> tuple[str, list[dict], dict | None]:
        """Single query method for non-interactive use.

        Returns:
            Tuple of (response_text, relevant_transactions, llm_stats)
            llm_stats is None if LLM was not used (e.g., price change queries)
        """
        # Check if this is a budget update request
        budget_response = self._handle_budget_update(query)
        if budget_response:
            # Budget updates don't have associated transactions
            self._last_transactions = []
            return budget_response, [], None

        # Check if user wants to expand search scope from previous query
        if self._is_scope_expansion_request(query) and self._last_search_query:
            # Re-search with previous query but force all history
            relevant_transactions = self._find_relevant_transactions(
                self._last_search_query, force_all_history=True
            )
            self._last_transactions = relevant_transactions
        # Check if this is a follow-up query about previous transactions
        elif self._is_follow_up_query(query) and self._last_transactions:
            relevant_transactions = self._last_transactions
        else:
            # New query - clear and search fresh
            self._last_transactions = []
            relevant_transactions = self._find_relevant_transactions(query)
            self._last_transactions = relevant_transactions
            self._last_search_query = query

        # For price change queries, bypass LLM and return deterministic response
        query_lower = query.lower()
        is_price_change_query = "price" in query_lower and (
            "increase" in query_lower or "change" in query_lower or
            "go up" in query_lower or "went up" in query_lower
        )
        if is_price_change_query and relevant_transactions:
            price_change = self._detect_price_change(relevant_transactions)
            merchant = self._extract_merchant_name(relevant_transactions)
            if price_change:
                # Extract details from price_change string: "PRICE INCREASED in June 2025 from R199.00 to R229.00"
                if "INCREASED" in price_change:
                    # Parse: "PRICE INCREASED in Month Year from R X to R Y"
                    match = re.search(r"in (.+?) from R([\d.]+) to R([\d.]+)", price_change)
                    if match:
                        month = match.group(1)
                        old_price = match.group(2)
                        new_price = match.group(3)
                        response = f"Your {merchant} price increased in {month} from R{old_price} to R{new_price}."
                        return response, relevant_transactions, None
                elif "DECREASED" in price_change:
                    match = re.search(r"in (.+?) from R([\d.]+) to R([\d.]+)", price_change)
                    if match:
                        month = match.group(1)
                        old_price = match.group(2)
                        new_price = match.group(3)
                        response = f"Your {merchant} price decreased in {month} from R{old_price} to R{new_price}."
                        return response, relevant_transactions, None
            else:
                # No price change detected
                response = f"Your {merchant} price has stayed the same."
                return response, relevant_transactions, None

        # For budget queries, bypass LLM and return deterministic response
        is_budget_query = "budget" in query_lower
        if is_budget_query:
            budgets = self.db.get_all_budgets()
            if budgets:
                latest_stmt = self.db.get_latest_statement()
                stmt_num = latest_stmt.get("statement_number") if latest_stmt else None

                # Build actual-spend lookup from latest statement
                actual_by_cat = {}
                if stmt_num:
                    category_summary = self.db.get_category_summary_for_statement(stmt_num)
                    actual_by_cat = {s["category"]: abs(s.get("total_debits", 0) or 0) for s in category_summary}

                budget_map = {b["category"]: b["amount"] for b in budgets}

                # Check if asking about a specific category
                categories = self.db.get_all_categories()
                asked_category = None
                for category in categories:
                    if category and category.lower().replace("_", " ") in query_lower:
                        asked_category = category
                        break

                if asked_category:
                    # Specific category budget
                    if asked_category in budget_map:
                        budget_amt = budget_map[asked_category]
                        actual = actual_by_cat.get(asked_category, 0)
                        remaining = budget_amt - actual
                        pct = (actual / budget_amt * 100) if budget_amt > 0 else 0
                        # Get transactions for this category from latest statement
                        if stmt_num:
                            txns = [
                                t for t in self.db.get_transactions_by_statement(stmt_num)
                                if t.get("category") == asked_category
                                and t.get("transaction_type") == "debit"
                            ]
                        else:
                            txns = self.db.get_transactions_by_category(asked_category)
                        if pct > 100:
                            response = (
                                f"Your **{asked_category}** budget is **R{budget_amt:,.2f}**. "
                                f"You've spent **R{actual:,.2f}** ({pct:.0f}% used), "
                                f"putting you **OVER BUDGET** by **R{abs(remaining):,.2f}**."
                            )
                        else:
                            response = (
                                f"Your **{asked_category}** budget is **R{budget_amt:,.2f}**. "
                                f"You've spent **R{actual:,.2f}** ({pct:.0f}% used), "
                                f"with **R{remaining:,.2f}** remaining."
                            )
                        return response, txns, None
                    else:
                        response = (
                            f"You haven't set a budget for {asked_category} yet. "
                            f"Say 'Set my {asked_category} budget to R5000' to create one."
                        )
                        return response, [], None
                else:
                    # Overall budget
                    total_budgeted = sum(b["amount"] for b in budgets)
                    total_spent = sum(actual_by_cat.get(b["category"], 0) for b in budgets)
                    total_remaining = total_budgeted - total_spent
                    pct = (total_spent / total_budgeted * 100) if total_budgeted > 0 else 0
                    if pct > 100:
                        response = (
                            f"Your overall budget is **R{total_budgeted:,.2f}**. "
                            f"You've spent **R{total_spent:,.2f}** ({pct:.0f}% used), "
                            f"putting you **OVER BUDGET** by **R{abs(total_remaining):,.2f}**."
                        )
                    else:
                        response = (
                            f"Your overall budget is **R{total_budgeted:,.2f}**. "
                            f"You've spent **R{total_spent:,.2f}** ({pct:.0f}% used), "
                            f"with **R{total_remaining:,.2f}** remaining."
                        )
                    return response, [], None
            else:
                return "You haven't set any budgets yet. Say 'Set my groceries budget to R5000' to create one.", [], None

        context = self._build_context(relevant_transactions, query)
        response = self._get_llm_response(query, context)
        return response, relevant_transactions, self._last_llm_stats

    def clear_context(self) -> None:
        """Clear conversation history and cached transactions."""
        self._conversation_history = []
        self._last_transactions = []
        self._last_search_query = ""
