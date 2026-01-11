#!/usr/bin/env python3
"""Bank Statement Chat Bot - CLI Entry Point."""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import pdfplumber
from rich.console import Console
from rich.table import Table

from .chat import ChatInterface
from .classifier import TransactionClassifier
from .config import get_config
from .database import Database
from .parsers import list_available_parsers
from .watcher import StatementWatcher, import_existing, reimport_statement


console = Console()


def cmd_import(args: argparse.Namespace, config: dict) -> None:
    """Import all PDF statements from the statements directory."""
    # Allow command-line overrides
    statements_dir = args.path if args.path else config["paths"]["statements_dir"]
    bank = args.bank if args.bank else config["bank"]

    db = Database(config["paths"]["database"])
    classifier = TransactionClassifier(
        host=config["ollama"]["host"],
        port=config["ollama"]["port"],
        model=config["ollama"]["model"],
        categories=config.get("categories"),
        classification_rules=config.get("classification_rules")
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

    console.print(f"[dim]Importing from: {statements_dir}[/dim]")
    console.print(f"[dim]Using parser: {bank}[/dim]\n")

    count = import_existing(
        statements_dir=statements_dir,
        db=db,
        bank=bank,
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
        categories=config.get("categories"),
        classification_rules=config.get("classification_rules")
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


def cmd_rename(args: argparse.Namespace, config: dict) -> None:
    """Rename statement PDFs to standardized format: {number}_{month}_{year}.pdf"""
    statements_dir = Path(config["paths"]["statements_dir"])

    if not statements_dir.exists():
        console.print(f"[red]Statements directory not found: {statements_dir}[/red]")
        sys.exit(1)

    # Pattern for already-renamed files: 287_Oct_2025.pdf
    expected_pattern = re.compile(r"^\d+_[A-Z][a-z]{2}_\d{4}\.pdf$")

    renamed = 0
    skipped = 0
    errors = 0

    for pdf_file in sorted(statements_dir.glob("*.pdf")):
        # Skip if already in correct format
        if expected_pattern.match(pdf_file.name):
            console.print(f"[dim]SKIP: {pdf_file.name} (already correct format)[/dim]")
            skipped += 1
            continue

        try:
            with pdfplumber.open(pdf_file) as pdf:
                text = pdf.pages[0].extract_text() or ""

            # Extract Tax Invoice/Statement Number (with or without spaces)
            match = re.search(r"Tax\s*Invoice/Statement\s*Number\s*[:\s]+(\d+)", text, re.IGNORECASE)
            if not match:
                console.print(f"[yellow]SKIP: {pdf_file.name} - no statement number found[/yellow]")
                skipped += 1
                continue
            statement_num = match.group(1)

            # Extract Statement Date (with or without spaces)
            match = re.search(r"Statement\s*Date\s*[:\s]+(\d{1,2}\s*\w+\s*\d{4})", text, re.IGNORECASE)
            if not match:
                console.print(f"[yellow]SKIP: {pdf_file.name} - no statement date found[/yellow]")
                skipped += 1
                continue

            # Parse date - handle with or without spaces
            date_str = match.group(1)
            # Add spaces if missing (e.g., "1February2025" -> "1 February 2025")
            date_str = re.sub(r"(\d+)([A-Za-z])", r"\1 \2", date_str)
            date_str = re.sub(r"([A-Za-z])(\d)", r"\1 \2", date_str)
            try:
                date_obj = datetime.strptime(date_str, "%d %B %Y")
            except ValueError:
                date_obj = datetime.strptime(date_str, "%d %b %Y")

            month = date_obj.strftime("%b")
            year = date_obj.strftime("%Y")

            new_name = f"{statement_num}_{month}_{year}.pdf"
            new_path = statements_dir / new_name

            if new_path.exists() and new_path != pdf_file:
                console.print(f"[yellow]SKIP: {pdf_file.name} -> {new_name} (target exists)[/yellow]")
                skipped += 1
                continue

            pdf_file.rename(new_path)
            console.print(f"[green]RENAMED: {pdf_file.name} -> {new_name}[/green]")
            renamed += 1

        except Exception as e:
            console.print(f"[red]ERROR: {pdf_file.name} - {e}[/red]")
            errors += 1

    console.print(f"\n[bold]Summary: {renamed} renamed, {skipped} skipped, {errors} errors[/bold]")


def cmd_reimport(args: argparse.Namespace, config: dict) -> None:
    """Re-import PDF statement(s) (deletes existing and re-imports)."""
    # Handle "all" as positional argument (bankbot reimport all)
    if args.file == "all":
        args.all = True
        args.file = None

    # Validate arguments
    if not args.all and not args.file:
        console.print("[red]Error: Must specify a file or use --all[/red]")
        sys.exit(1)

    bank = args.bank if args.bank else config["bank"]

    db = Database(config["paths"]["database"])
    classifier = TransactionClassifier(
        host=config["ollama"]["host"],
        port=config["ollama"]["port"],
        model=config["ollama"]["model"],
        categories=config.get("categories"),
        classification_rules=config.get("classification_rules")
    )

    # Check Ollama connection
    if not classifier.check_connection():
        console.print(
            f"[red]Cannot connect to Ollama or model '{config['ollama']['model']}' "
            f"not found.[/red]"
        )
        sys.exit(1)

    if args.all:
        # Reimport all PDF files
        statements_dir = Path(config["paths"]["statements_dir"])
        pdf_files = sorted(statements_dir.glob("*.pdf"))

        if not pdf_files:
            console.print(f"[yellow]No PDF files found in {statements_dir}[/yellow]")
            return

        console.print(f"[bold]Re-importing {len(pdf_files)} PDF files...[/bold]\n")

        success_count = 0
        fail_count = 0

        for pdf_path in pdf_files:
            console.print(f"[dim]Re-importing: {pdf_path.name}[/dim]")
            success = reimport_statement(
                pdf_path=pdf_path,
                db=db,
                bank=bank,
                classifier=classifier
            )
            if success:
                success_count += 1
            else:
                fail_count += 1
                console.print(f"[red]Failed: {pdf_path.name}[/red]")

        console.print(f"\n[bold]Summary: {success_count} succeeded, {fail_count} failed[/bold]")
    else:
        # Reimport single file
        pdf_path = Path(args.file)

        if not pdf_path.exists():
            console.print(f"[red]File not found: {pdf_path}[/red]")
            sys.exit(1)

        console.print(f"[dim]Re-importing: {pdf_path}[/dim]")
        console.print(f"[dim]Using parser: {bank}[/dim]\n")

        success = reimport_statement(
            pdf_path=pdf_path,
            db=db,
            bank=bank,
            classifier=classifier
        )

        if success:
            console.print("\n[bold green]Re-import completed successfully[/bold green]")
        else:
            console.print("\n[bold red]Re-import failed[/bold red]")
            sys.exit(1)


def cmd_serve(args: argparse.Namespace, config: dict) -> None:
    """Start the API server."""
    import uvicorn

    from .api.app import app

    host = args.host
    port = args.port

    console.print(f"[bold green]Starting API server...[/bold green]")
    console.print(f"[dim]WebSocket: ws://{host}:{port}/ws/chat[/dim]")
    console.print(f"[dim]REST API:  http://{host}:{port}/api/v1/...[/dim]")
    console.print(f"[dim]API Docs:  http://{host}:{port}/docs[/dim]")
    console.print()

    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bank Statement Chat Bot - Parse and query your bank statements with AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s import               Import all PDFs from statements directory
  %(prog)s watch                Watch for new statements and auto-import
  %(prog)s chat                 Start interactive chat
  %(prog)s list                 List recent transactions
  %(prog)s search "doctor"      Search for transactions
  %(prog)s categories           Show spending by category
  %(prog)s reimport 288_Dec.pdf Re-import a specific statement
        """
    )

    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to config file (default: config.yaml)"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Import command
    import_parser = subparsers.add_parser("import", help="Import PDF statements")
    import_parser.add_argument("--path", help="Path to statements directory (overrides config)")
    import_parser.add_argument("--bank", help="Bank parser to use (overrides config)")

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

    # Rename command
    subparsers.add_parser("rename", help="Rename PDFs to {number}_{month}_{year}.pdf format")

    # Reimport command
    reimport_parser = subparsers.add_parser("reimport", help="Re-import PDF statement(s)")
    reimport_parser.add_argument("file", nargs="?", help="Path to the PDF file to re-import")
    reimport_parser.add_argument("--all", action="store_true", help="Re-import all PDF files in statements directory")
    reimport_parser.add_argument("--bank", help="Bank parser to use (overrides config)")

    # Serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind to (default: 8000)")

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
        "rename": cmd_rename,
        "reimport": cmd_reimport,
        "serve": cmd_serve,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
