"""Directory watcher for automatic statement import."""

import re
import time
from pathlib import Path

from rich.console import Console
from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from watchdog.observers import Observer

from .classifier import TransactionClassifier
from .database import Database
from .parsers import get_parser


class StatementHandler(FileSystemEventHandler):
    """Handle new PDF files in the statements directory."""

    def __init__(
        self,
        db: Database,
        bank: str,
        classifier: TransactionClassifier,
        console: Console | None = None,
        pdf_password: str | None = None
    ):
        self.db = db
        self.bank = bank
        self.classifier = classifier
        self.console = console or Console()
        self._parser = get_parser(bank)
        self._pdf_password = pdf_password

    def on_created(self, event: FileCreatedEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return

        path = Path(event.src_path)

        # Only process PDF files
        if path.suffix.lower() != ".pdf":
            return

        # Wait a moment for file to be fully written
        time.sleep(0.5)

        self._process_file(path)

    def _process_file(self, pdf_path: Path) -> None:
        """Process a single PDF file."""
        filename = pdf_path.name

        # Skip if already imported
        if self.db.statement_exists(filename):
            self.console.print(f"[yellow]Skipping {filename} (already imported)[/yellow]")
            return

        self.console.print(f"[cyan]Processing {filename}...[/cyan]")

        try:
            # Parse the statement
            statement_data = self._parser.parse(pdf_path, password=self._pdf_password)

            # Insert statement record
            statement_id = self.db.insert_statement(
                filename=filename,
                account_number=statement_data.account_number,
                statement_date=statement_data.statement_date,
                statement_number=statement_data.statement_number
            )

            # Process and classify transactions
            transactions_to_insert = []
            for tx in statement_data.transactions:
                # Determine transaction type
                tx_type = "credit" if tx.amount > 0 else "debit"

                # Classify with LLM
                classification = self.classifier.classify(tx.description, tx.amount)

                transactions_to_insert.append({
                    "date": tx.date,
                    "description": tx.description,
                    "amount": abs(tx.amount),
                    "balance": tx.balance,
                    "transaction_type": tx_type,
                    "category": classification.category,
                    "recipient_or_payer": classification.recipient_or_payer,
                    "reference": tx.reference,
                    "raw_text": tx.raw_text
                })

            # Batch insert
            self.db.insert_transactions_batch(statement_id, transactions_to_insert)

            self.console.print(
                f"[green]Imported {len(transactions_to_insert)} transactions "
                f"from {filename}[/green]"
            )

        except Exception as e:
            self.console.print(f"[red]Error processing {filename}: {e}[/red]")


class StatementWatcher:
    """Watch a directory for new bank statements."""

    def __init__(
        self,
        statements_dir: str | Path,
        db: Database,
        bank: str,
        classifier: TransactionClassifier,
        pdf_password: str | None = None
    ):
        self.statements_dir = Path(statements_dir)
        self.db = db
        self.bank = bank
        self.classifier = classifier
        self.console = Console()
        self._observer = None
        self._pdf_password = pdf_password

    def start(self) -> None:
        """Start watching for new files."""
        if not self.statements_dir.exists():
            self.statements_dir.mkdir(parents=True)

        handler = StatementHandler(
            db=self.db,
            bank=self.bank,
            classifier=self.classifier,
            console=self.console,
            pdf_password=self._pdf_password
        )

        self._observer = Observer()
        self._observer.schedule(handler, str(self.statements_dir), recursive=False)
        self._observer.start()

        self.console.print(
            f"[green]Watching {self.statements_dir} for new statements...[/green]"
        )
        self.console.print("[dim]Press Ctrl+C to stop[/dim]\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Stop watching."""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self.console.print("\n[dim]Stopped watching.[/dim]")


def import_existing(
    statements_dir: str | Path,
    db: Database,
    bank: str,
    classifier: TransactionClassifier,
    pdf_password: str | None = None
) -> int:
    """Import all existing PDF files in the statements directory.

    Returns:
        Number of statements imported
    """
    statements_dir = Path(statements_dir)
    console = Console()

    if not statements_dir.exists():
        statements_dir.mkdir(parents=True)
        console.print(f"[yellow]Created {statements_dir}[/yellow]")
        return 0

    parser = get_parser(bank)
    pdf_files = list(statements_dir.glob("*.pdf")) + list(statements_dir.glob("*.PDF"))

    # Sort by statement number if filename matches format: {number}_{month}_{year}.pdf
    def sort_key(path: Path) -> tuple:
        match = re.match(r"^(\d+)_", path.name)
        if match:
            return (0, int(match.group(1)), path.name)
        return (1, 0, path.name)  # Non-matching files come after

    pdf_files = sorted(pdf_files, key=sort_key)

    if not pdf_files:
        console.print(f"[yellow]No PDF files found in {statements_dir}[/yellow]")
        return 0

    imported = 0
    for pdf_path in pdf_files:
        filename = pdf_path.name

        if db.statement_exists(filename):
            console.print(f"[dim]Skipping {filename} (already imported)[/dim]")
            continue

        console.print(f"[cyan]Processing {filename}...[/cyan]")

        try:
            statement_data = parser.parse(pdf_path, password=pdf_password)

            statement_id = db.insert_statement(
                filename=filename,
                account_number=statement_data.account_number,
                statement_date=statement_data.statement_date,
                statement_number=statement_data.statement_number
            )

            transactions_to_insert = []
            for tx in statement_data.transactions:
                tx_type = "credit" if tx.amount > 0 else "debit"
                classification = classifier.classify(tx.description, tx.amount)

                transactions_to_insert.append({
                    "date": tx.date,
                    "description": tx.description,
                    "amount": abs(tx.amount),
                    "balance": tx.balance,
                    "transaction_type": tx_type,
                    "category": classification.category,
                    "recipient_or_payer": classification.recipient_or_payer,
                    "reference": tx.reference,
                    "raw_text": tx.raw_text
                })

            db.insert_transactions_batch(statement_id, transactions_to_insert)

            console.print(
                f"[green]Imported {len(transactions_to_insert)} transactions[/green]"
            )
            imported += 1

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    return imported


def reimport_statement(
    pdf_path: str | Path,
    db: Database,
    bank: str,
    classifier: TransactionClassifier,
    pdf_password: str | None = None
) -> bool:
    """Re-import a specific PDF statement (delete existing and re-import).

    Returns:
        True if successful, False if failed
    """
    pdf_path = Path(pdf_path)
    console = Console()

    if not pdf_path.exists():
        console.print(f"[red]File not found: {pdf_path}[/red]")
        return False

    filename = pdf_path.name
    parser = get_parser(bank)

    # Delete existing statement and transactions
    if db.delete_statement_by_filename(filename):
        console.print(f"[yellow]Deleted existing import of {filename}[/yellow]")

    console.print(f"[cyan]Processing {filename}...[/cyan]")

    try:
        statement_data = parser.parse(pdf_path, password=pdf_password)

        statement_id = db.insert_statement(
            filename=filename,
            account_number=statement_data.account_number,
            statement_date=statement_data.statement_date,
            statement_number=statement_data.statement_number
        )

        transactions_to_insert = []
        for tx in statement_data.transactions:
            tx_type = "credit" if tx.amount > 0 else "debit"
            classification = classifier.classify(tx.description, tx.amount)

            transactions_to_insert.append({
                "date": tx.date,
                "description": tx.description,
                "amount": abs(tx.amount),
                "balance": tx.balance,
                "transaction_type": tx_type,
                "category": classification.category,
                "recipient_or_payer": classification.recipient_or_payer,
                "reference": tx.reference,
                "raw_text": tx.raw_text
            })

        db.insert_transactions_batch(statement_id, transactions_to_insert)

        console.print(
            f"[green]Imported {len(transactions_to_insert)} transactions[/green]"
        )
        return True

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        return False
