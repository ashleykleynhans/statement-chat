#!/usr/bin/env python3
"""Bank Statement Chat Bot - CLI Entry Point."""

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .chat import ChatInterface
from .classifier import TransactionClassifier
from .config import get_config
from .database import Database
from .parsers import list_available_parsers
from .watcher import StatementWatcher, import_existing


console = Console()


def cmd_import(args: argparse.Namespace, config: dict) -> None:
    """Import all PDF statements from the statements directory."""
    db = Database(config["paths"]["database"])
    classifier = TransactionClassifier(
        host=config["ollama"]["host"],
        port=config["ollama"]["port"],
        model=config["ollama"]["model"],
        categories=config.get("categories")
    )

    # Check Ollama connection
    if not classifier.check_connection():
        console.print(
            f"[red]Cannot connect to Ollama or model '{config['ollama']['model']}' "
            f"not found.[/red]"
        )
        console.print(
            f"[yellow]Available models: {classifier.get_available_models() or 'none'}[/yellow]"
        )
        console.print("[dim]Start Ollama with: ollama serve[/dim]")
        sys.exit(1)

    count = import_existing(
        statements_dir=config["paths"]["statements_dir"],
        db=db,
        bank=config["bank"],
        classifier=classifier
    )

    console.print(f"\n[bold]Imported {count} new statement(s)[/bold]")


def cmd_watch(args: argparse.Namespace, config: dict) -> None:
    """Watch for new statements and import them automatically."""
    db = Database(config["paths"]["database"])
    classifier = TransactionClassifier(
        host=config["ollama"]["host"],
        port=config["ollama"]["port"],
        model=config["ollama"]["model"],
        categories=config.get("categories")
    )

    if not classifier.check_connection():
        console.print(
            f"[red]Cannot connect to Ollama or model '{config['ollama']['model']}' "
            f"not found.[/red]"
        )
        sys.exit(1)

    watcher = StatementWatcher(
        statements_dir=config["paths"]["statements_dir"],
        db=db,
        bank=config["bank"],
        classifier=classifier
    )
    watcher.start()


def cmd_chat(args: argparse.Namespace, config: dict) -> None:
    """Start interactive chat interface."""
    db = Database(config["paths"]["database"])

    stats = db.get_stats()
    if stats["total_transactions"] == 0:
        console.print("[yellow]No transactions in database.[/yellow]")
        console.print(
            f"[dim]Place PDF statements in {config['paths']['statements_dir']} "
            f"and run 'import' first.[/dim]"
        )
        sys.exit(1)

    chat = ChatInterface(
        db=db,
        host=config["ollama"]["host"],
        port=config["ollama"]["port"],
        model=config["ollama"]["model"]
    )
    chat.start()


def cmd_list(args: argparse.Namespace, config: dict) -> None:
    """List transactions."""
    db = Database(config["paths"]["database"])

    limit = args.limit or 20
    transactions = db.get_all_transactions(limit=limit)

    if not transactions:
        console.print("[yellow]No transactions found.[/yellow]")
        return

    table = Table(title=f"Recent Transactions (showing {len(transactions)})")
    table.add_column("Date", style="cyan")
    table.add_column("Description")
    table.add_column("Amount", justify="right")
    table.add_column("Type", style="dim")
    table.add_column("Category", style="magenta")

    for tx in transactions:
        amount = tx.get("amount", 0)
        tx_type = tx.get("transaction_type", "")

        if tx_type == "debit":
            amount_str = f"[red]-R{amount:.2f}[/red]"
        else:
            amount_str = f"[green]+R{amount:.2f}[/green]"

        table.add_row(
            tx.get("date", ""),
            tx.get("description", "")[:40],
            amount_str,
            tx_type,
            tx.get("category", "") or "-"
        )

    console.print(table)


def cmd_categories(args: argparse.Namespace, config: dict) -> None:
    """Show transaction categories and spending summary."""
    db = Database(config["paths"]["database"])

    summary = db.get_category_summary()

    if not summary:
        console.print("[yellow]No transactions found.[/yellow]")
        return

    table = Table(title="Spending by Category")
    table.add_column("Category")
    table.add_column("Count", justify="right")
    table.add_column("Total Debits", justify="right", style="red")
    table.add_column("Total Credits", justify="right", style="green")

    for row in summary:
        table.add_row(
            row.get("category") or "uncategorized",
            str(row.get("count", 0)),
            f"R{row.get('total_debits', 0):.2f}",
            f"R{row.get('total_credits', 0):.2f}"
        )

    console.print(table)


def cmd_stats(args: argparse.Namespace, config: dict) -> None:
    """Show database statistics."""
    db = Database(config["paths"]["database"])
    stats = db.get_stats()

    table = Table(title="Database Statistics")
    table.add_column("Metric")
    table.add_column("Value", justify="right")

    table.add_row("Total Statements", str(stats.get("total_statements", 0)))
    table.add_row("Total Transactions", str(stats.get("total_transactions", 0)))
    table.add_row("Total Debits", f"R{stats.get('total_debits', 0):.2f}")
    table.add_row("Total Credits", f"R{stats.get('total_credits', 0):.2f}")
    table.add_row("Categories", str(stats.get("categories_count", 0)))

    console.print(table)


def cmd_search(args: argparse.Namespace, config: dict) -> None:
    """Search transactions."""
    db = Database(config["paths"]["database"])

    results = db.search_transactions(args.term)

    if not results:
        console.print(f"[yellow]No transactions matching '{args.term}'[/yellow]")
        return

    table = Table(title=f"Search Results: '{args.term}' ({len(results)} found)")
    table.add_column("Date", style="cyan")
    table.add_column("Description")
    table.add_column("Amount", justify="right")
    table.add_column("Category", style="magenta")

    for tx in results[:50]:
        amount = tx.get("amount", 0)
        tx_type = tx.get("transaction_type", "")

        if tx_type == "debit":
            amount_str = f"[red]-R{amount:.2f}[/red]"
        else:
            amount_str = f"[green]+R{amount:.2f}[/green]"

        table.add_row(
            tx.get("date", ""),
            tx.get("description", "")[:50],
            amount_str,
            tx.get("category", "") or "-"
        )

    console.print(table)


def cmd_parsers(args: argparse.Namespace, config: dict) -> None:
    """List available bank parsers."""
    parsers = list_available_parsers()
    current = config.get("bank", "")

    console.print("[bold]Available Bank Parsers:[/bold]")
    for parser in parsers:
        marker = " [green](active)[/green]" if parser == current else ""
        console.print(f"  - {parser}{marker}")

    if not parsers:
        console.print("  [dim]No parsers available[/dim]")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bank Statement Chat Bot - Parse and query your bank statements with AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s import          Import all PDFs from statements directory
  %(prog)s watch           Watch for new statements and auto-import
  %(prog)s chat            Start interactive chat
  %(prog)s list            List recent transactions
  %(prog)s search "doctor" Search for transactions
  %(prog)s categories      Show spending by category
        """
    )

    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Import command
    subparsers.add_parser("import", help="Import PDF statements")

    # Watch command
    subparsers.add_parser("watch", help="Watch for new statements")

    # Chat command
    subparsers.add_parser("chat", help="Start interactive chat")

    # List command
    list_parser = subparsers.add_parser("list", help="List transactions")
    list_parser.add_argument("-n", "--limit", type=int, help="Number of transactions")

    # Categories command
    subparsers.add_parser("categories", help="Show category summary")

    # Stats command
    subparsers.add_parser("stats", help="Show database statistics")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search transactions")
    search_parser.add_argument("term", help="Search term")

    # Parsers command
    subparsers.add_parser("parsers", help="List available bank parsers")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Load config
    try:
        config = get_config() if args.config == "config.yaml" else __import__("yaml").safe_load(open(args.config))
    except FileNotFoundError:
        console.print(f"[red]Config file not found: {args.config}[/red]")
        console.print("[dim]Create config.yaml or specify path with -c[/dim]")
        sys.exit(1)

    # Dispatch command
    commands = {
        "import": cmd_import,
        "watch": cmd_watch,
        "chat": cmd_chat,
        "list": cmd_list,
        "categories": cmd_categories,
        "stats": cmd_stats,
        "search": cmd_search,
        "parsers": cmd_parsers,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
