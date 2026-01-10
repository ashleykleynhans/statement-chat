"""Chat interface for querying bank transactions with Ollama."""

import json
import re
from datetime import datetime, timedelta

import ollama
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
        self._client = ollama.Client(host=f"http://{host}:{port}")
        self.console = Console()
        self._conversation_history = []
        self._last_transactions = []  # Store last query's transactions for follow-ups

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

    def _process_query(self, query: str) -> None:
        """Process a user query and display the response."""
        # Check if this is a follow-up query about previous transactions
        if self._is_follow_up_query(query) and self._last_transactions:
            relevant_transactions = self._last_transactions
        else:
            # Find new relevant transactions
            relevant_transactions = self._find_relevant_transactions(query)
            # Store for potential follow-up queries
            self._last_transactions = relevant_transactions

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

        # Pronouns/references that indicate follow-up
        follow_up_indicators = {
            "them", "these", "those", "it", "they",
            "above", "previous", "that",
            "group", "sort", "filter", "summarize", "total",
            "sum", "average", "breakdown", "analyze"
        }

        # Check for follow-up indicators (word-based match)
        if words & follow_up_indicators:
            return True

        # If query has no specific transaction keywords, might be follow-up
        has_specific_keywords = any(word in query_lower for word in [
            "show", "find", "search", "electricity", "groceries", "fuel",
            "medical", "salary", "deposit", "last month", "this month"
        ])

        # Short queries without specific keywords are likely follow-ups
        if len(query.split()) <= 5 and not has_specific_keywords:
            return True

        return False

    def _find_relevant_transactions(self, query: str) -> list[dict]:
        """Find transactions relevant to the user's query."""
        query_lower = query.lower()

        # First, determine date range if specified
        date_start = None
        date_end = None

        if "last month" in query_lower:
            today = datetime.now()
            date_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            date_end = today.replace(day=1) - timedelta(days=1)
        elif "this month" in query_lower:
            today = datetime.now()
            date_start = today.replace(day=1)
            date_end = today

        # Check for category keywords
        categories = self.db.get_all_categories()
        matched_category = None
        for category in categories:
            if category and category.lower() in query_lower:
                matched_category = category
                break

        # If query is about budget, filter to latest statement only
        is_budget_query = "budget" in query_lower
        if is_budget_query:
            latest_stmt = self.db.get_latest_statement()
            if latest_stmt and latest_stmt.get("statement_number"):
                stmt_num = latest_stmt["statement_number"]
                stmt_transactions = self.db.get_transactions_by_statement(stmt_num)
                if matched_category:
                    return [tx for tx in stmt_transactions if tx.get("category") == matched_category]
                return stmt_transactions

        # If we have both date range and category, filter by both
        if date_start and date_end and matched_category:
            all_in_range = self.db.get_transactions_in_date_range(
                date_start.strftime("%Y-%m-%d"),
                date_end.strftime("%Y-%m-%d")
            )
            return [tx for tx in all_in_range if tx.get("category") == matched_category]

        # If only category specified
        if matched_category:
            return self.db.get_transactions_by_category(matched_category)

        # If only date range specified
        if date_start and date_end:
            return self.db.get_transactions_in_date_range(
                date_start.strftime("%Y-%m-%d"),
                date_end.strftime("%Y-%m-%d")
            )

        # Check for transaction type
        if "credit" in query_lower or "deposit" in query_lower or "income" in query_lower:
            return self.db.get_transactions_by_type("credit")
        if "debit" in query_lower or "expense" in query_lower or "payment" in query_lower:
            # Don't return all debits, too many - let search narrow it down
            pass

        # Extract potential search terms
        search_terms = self._extract_search_terms(query)
        for term in search_terms:
            results = self.db.search_transactions(term)
            if results:
                return results

        # Fall back to recent transactions
        return self.db.get_all_transactions(limit=20)

    def _extract_search_terms(self, query: str) -> list[str]:
        """Extract potential search terms from query."""
        # Remove common words
        stop_words = {
            "when", "did", "i", "the", "a", "an", "to", "for", "of", "in",
            "my", "me", "last", "first", "how", "much", "many", "what",
            "where", "why", "show", "find", "get", "list", "all", "pay",
            "paid", "spend", "spent", "make", "made", "payment", "payments"
        }

        words = re.findall(r"\b[a-zA-Z]+\b", query.lower())
        terms = [w for w in words if w not in stop_words and len(w) > 2]

        return terms

    def _build_context(self, transactions: list[dict], query: str) -> str:
        """Build context string for LLM from transactions."""
        if not transactions:
            return "No matching transactions found in the database."

        stats = self.db.get_stats()
        query_lower = query.lower()

        context_parts = [
            f"Database contains {stats['total_transactions']} transactions.",
            f"Found {len(transactions)} potentially relevant transactions.",
        ]

        # If query is about budget, include budget info
        if "budget" in query_lower:
            budgets = self.db.get_all_budgets()
            latest_stmt = self.db.get_latest_statement()

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
                            f"- {cat}: R{actual:.2f} spent of R{budget_amt:.2f} budget "
                            f"(R{remaining:.2f} remaining, {status})"
                        )

                    total_remaining = total_budgeted - total_spent
                    context_parts.append(
                        f"\nOVERALL BUDGET TOTAL: R{total_budgeted:.2f} budgeted, "
                        f"R{total_spent:.2f} spent, R{total_remaining:.2f} remaining"
                    )

        context_parts.append("\nRelevant transactions:")

        # Limit to most relevant transactions for context
        total_debits = 0.0
        total_credits = 0.0
        for tx in transactions[:15]:
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
            line += f" | R{abs(amount):.2f} {tx_type} | {category}"
            context_parts.append(line)

        if len(transactions) > 15:
            context_parts.append(f"\n... and {len(transactions) - 15} more transactions")

        # Provide pre-calculated totals
        context_parts.append(f"\nTOTAL of above transactions: R{total_debits:.2f} spent (debits), R{total_credits:.2f} received (credits)")

        return "\n".join(context_parts)

    def _get_llm_response(self, query: str, context: str) -> str:
        """Get response from Ollama LLM."""
        today = datetime.now()
        current_date = today.strftime("%Y-%m-%d")
        current_month = today.strftime("%B %Y")
        last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%B %Y")

        system_prompt = f"""You are a helpful assistant that answers questions about bank transactions.
Be concise and direct. Use South African Rand (R) for amounts.
Always address the user as "you"/"your", never "the user".

When listing spending or transactions:
- List each transaction with its date and amount
- Use the pre-calculated TOTAL provided in the context - never calculate totals yourself
- Example format:
  "You spent R27,030.98 on ceiling repairs:
  - 15 Jan 2024: R9,460.84
  - 20 Feb 2024: R17,570.14"

For budget questions:
- If asked about a specific category, report that category's budget status
- If asked about overall/total budget, use the OVERALL BUDGET TOTAL from the context
- Each category has its own separate budget - don't mix them

Today is {current_date}. Current month: {current_month}. Last month: {last_month}."""

        user_message = f"""Context:
{context}

Question: {query}

Answer concisely and directly."""

        # Add user message to history
        self._conversation_history.append({
            "role": "user",
            "content": user_message
        })

        try:
            # Build messages with system prompt and conversation history
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(self._conversation_history)

            response = self._client.chat(
                model=self.model,
                messages=messages,
                options={"temperature": 0.3}
            )
            assistant_response = response["message"]["content"].strip()

            # Add assistant response to history
            self._conversation_history.append({
                "role": "assistant",
                "content": assistant_response
            })

            return assistant_response
        except Exception as e:
            # Remove the failed user message from history
            self._conversation_history.pop()
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

    def ask(self, query: str) -> str:
        """Single query method for non-interactive use."""
        relevant_transactions = self._find_relevant_transactions(query)
        context = self._build_context(relevant_transactions, query)
        return self._get_llm_response(query, context)
