"""Base class for bank statement parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Transaction:
    """A single transaction from a bank statement."""
    date: str
    description: str
    amount: float
    balance: float | None = None
    reference: str | None = None
    raw_text: str = ""


@dataclass
class StatementData:
    """Parsed data from a bank statement."""
    account_number: str | None = None
    statement_date: str | None = None
    statement_number: str | None = None
    transactions: list[Transaction] = field(default_factory=list)


class BaseBankParser(ABC):
    """Abstract base class for bank statement parsers.

    To add support for a new bank:
    1. Create a new file in src/parsers/ (e.g., standardbank.py)
    2. Create a class that inherits from BaseBankParser
    3. Implement the parse() and bank_name() methods
    4. The parser will be auto-discovered by the registry
    """

    @abstractmethod
    def parse(self, pdf_path: str | Path, password: str | None = None) -> StatementData:
        """Parse a PDF statement and return extracted data.

        Args:
            pdf_path: Path to the PDF file to parse
            password: Optional password for encrypted PDFs

        Returns:
            StatementData object with account info and transactions
        """
        pass

    @classmethod
    @abstractmethod
    def bank_name(cls) -> str:
        """Return the bank identifier (e.g., 'fnb', 'standardbank').

        This is used to match the config.yaml bank setting.
        """
        pass

    def _determine_transaction_type(self, amount: float) -> str:
        """Determine if transaction is debit or credit based on amount sign."""
        return "credit" if amount > 0 else "debit"
