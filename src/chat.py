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

    def start(self) -> None:
        """Start the interactive chat loop."""
        self.console.print(Panel(
            "[bold green]Bank Statement Chat[/bold green]\n\n"
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
        # First, try to understand what data the user needs
        relevant_transactions = self._find_relevant_transactions(query)

        # Build context for the LLM
        context = self._build_context(relevant_transactions, query)

        # Get LLM response
        response = self._get_llm_response(query, context)

        self.console.print(f"\n[bold green]Assistant:[/bold green] {response}\n")

        # Show relevant transactions if found
        if relevant_transactions and len(relevant_transactions) <= 10:
            self._display_transactions(relevant_transactions)

    def _find_relevant_transactions(self, query: str) -> list[dict]:
        """Find transactions relevant to the user's query."""
        query_lower = query.lower()

        # Check for category keywords
        categories = self.db.get_all_categories()
        for category in categories:
            if category and category.lower() in query_lower:
                return self.db.get_transactions_by_category(category)

        # Check for transaction type
        if "credit" in query_lower or "deposit" in query_lower or "income" in query_lower:
            return self.db.get_transactions_by_type("credit")
        if "debit" in query_lower or "expense" in query_lower or "payment" in query_lower:
            # Don't return all debits, too many - let search narrow it down
            pass

        # Check for time-based queries
        if "last month" in query_lower:
            today = datetime.now()
            start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
            end = today.replace(day=1) - timedelta(days=1)
            return self.db.get_transactions_in_date_range(
                start.strftime("%Y-%m-%d"),
                end.strftime("%Y-%m-%d")
            )
        if "this month" in query_lower:
            today = datetime.now()
            start = today.replace(day=1)
            return self.db.get_transactions_in_date_range(
                start.strftime("%Y-%m-%d"),
                today.strftime("%Y-%m-%d")
            )

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

        context_parts = [
            f"Database contains {stats['total_transactions']} transactions.",
            f"Found {len(transactions)} potentially relevant transactions.",
            "\nRelevant transactions:"
        ]

        # Limit to most relevant transactions for context
        for tx in transactions[:15]:
            date = tx.get("date", "Unknown")
            desc = tx.get("description", "")[:50]
            amount = tx.get("amount", 0)
            category = tx.get("category", "uncategorized")
            tx_type = tx.get("transaction_type", "unknown")
            recipient = tx.get("recipient_or_payer", "")

            line = f"- {date}: {desc}"
            if recipient:
                line += f" ({recipient})"
            line += f" | R{abs(amount):.2f} {tx_type} | {category}"
            context_parts.append(line)

        if len(transactions) > 15:
            context_parts.append(f"\n... and {len(transactions) - 15} more transactions")

        return "\n".join(context_parts)

    def _get_llm_response(self, query: str, context: str) -> str:
        """Get response from Ollama LLM."""
        system_prompt = """You are a helpful assistant that answers questions about bank transactions.
You have access to the user's transaction history. Be concise and helpful.
When mentioning amounts, use South African Rand (R) currency.
If you can't find the specific information requested, say so and suggest what else might be helpful."""

        prompt = f"""Context about the user's transactions:
{context}

User question: {query}

Please provide a helpful, concise answer based on the transaction data above."""

        try:
            response = self._client.generate(
                model=self.model,
                prompt=prompt,
                system=system_prompt,
                options={"temperature": 0.3}
            )
            return response["response"].strip()
        except Exception as e:
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
