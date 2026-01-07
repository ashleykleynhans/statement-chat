"""FNB (First National Bank) statement parser."""

import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from . import register_parser
from .base import BaseBankParser, StatementData, Transaction


@register_parser
class FNBParser(BaseBankParser):
    """Parser for FNB bank statements.

    Note: This parser is designed for standard FNB statement PDFs.
    The parsing logic may need adjustment based on the specific
    statement format you receive.
    """

    @classmethod
    def bank_name(cls) -> str:
        return "fnb"

    def parse(self, pdf_path: str | Path) -> StatementData:
        """Parse an FNB statement PDF."""
        pdf_path = Path(pdf_path)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        transactions = []
        account_number = None
        statement_date = None

        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"

                # Try to extract account number from first page
                if account_number is None:
                    account_number = self._extract_account_number(page_text)

                # Try to extract statement date
                if statement_date is None:
                    statement_date = self._extract_statement_date(page_text)

                # Extract transactions from tables if present
                tables = page.extract_tables()
                for table in tables:
                    transactions.extend(self._parse_table(table))

            # If no tables found, try line-by-line parsing
            if not transactions:
                transactions = self._parse_text(full_text)

        return StatementData(
            account_number=account_number,
            statement_date=statement_date,
            transactions=transactions
        )

    def _extract_account_number(self, text: str) -> str | None:
        """Extract account number from statement text."""
        patterns = [
            r"Account\s*(?:Number|No\.?|#)?\s*[:\s]?\s*(\d{10,})",
            r"Acc(?:ount)?\s*(?:No\.?|#)?\s*[:\s]?\s*(\d{10,})",
            r"(\d{10,})\s*(?:Cheque|Current|Savings)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_statement_date(self, text: str) -> str | None:
        """Extract statement date from text."""
        patterns = [
            r"Statement\s*(?:Date|Period)?\s*[:\s]?\s*(\d{1,2}[\s/-]\w+[\s/-]\d{2,4})",
            r"(?:From|Period):\s*\d{1,2}[\s/-]\w+[\s/-]\d{2,4}\s*(?:to|[-–])\s*(\d{1,2}[\s/-]\w+[\s/-]\d{2,4})",
            r"(\d{1,2}[\s/-]\w{3,9}[\s/-]\d{2,4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self._normalize_date(match.group(1))
        return None

    def _normalize_date(self, date_str: str) -> str | None:
        """Convert various date formats to YYYY-MM-DD."""
        date_formats = [
            "%d %B %Y",
            "%d %b %Y",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%d %B %y",
            "%d %b %y",
            "%d/%m/%y",
            "%d-%m-%y",
        ]

        date_str = date_str.strip().replace("  ", " ")

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    def _parse_table(self, table: list[list]) -> list[Transaction]:
        """Parse transactions from a table structure."""
        transactions = []

        if not table or len(table) < 2:
            return transactions

        # Try to identify column indices
        header = table[0] if table[0] else []
        header_lower = [str(h).lower() if h else "" for h in header]

        date_col = self._find_column(header_lower, ["date", "trans date", "transaction date"])
        desc_col = self._find_column(header_lower, ["description", "details", "particulars", "transaction"])
        amount_col = self._find_column(header_lower, ["amount", "debit", "credit"])
        balance_col = self._find_column(header_lower, ["balance", "running balance"])
        ref_col = self._find_column(header_lower, ["reference", "ref", "ref no"])

        # If we couldn't identify columns, try positional parsing
        if date_col is None:
            return self._parse_table_positional(table)

        for row in table[1:]:
            if not row or len(row) <= max(filter(None, [date_col, desc_col, amount_col])):
                continue

            try:
                date_str = str(row[date_col]).strip() if date_col is not None and row[date_col] else ""
                if not date_str or not self._looks_like_date(date_str):
                    continue

                date = self._normalize_date(date_str)
                description = str(row[desc_col]).strip() if desc_col is not None and row[desc_col] else ""
                amount_str = str(row[amount_col]).strip() if amount_col is not None and row[amount_col] else "0"
                balance_str = str(row[balance_col]).strip() if balance_col is not None and balance_col < len(row) and row[balance_col] else None
                reference = str(row[ref_col]).strip() if ref_col is not None and ref_col < len(row) and row[ref_col] else None

                amount = self._parse_amount(amount_str)
                balance = self._parse_amount(balance_str) if balance_str else None

                if date and description:
                    transactions.append(Transaction(
                        date=date,
                        description=description,
                        amount=amount,
                        balance=balance,
                        reference=reference,
                        raw_text=" | ".join(str(c) for c in row if c)
                    ))
            except (IndexError, ValueError):
                continue

        return transactions

    def _parse_table_positional(self, table: list[list]) -> list[Transaction]:
        """Parse table assuming standard column positions."""
        transactions = []

        for row in table[1:]:  # Skip header
            if not row or len(row) < 3:
                continue

            # Common FNB format: Date | Description | Amount | Balance
            try:
                date_str = str(row[0]).strip() if row[0] else ""
                if not self._looks_like_date(date_str):
                    continue

                date = self._normalize_date(date_str)
                description = str(row[1]).strip() if len(row) > 1 and row[1] else ""
                amount_str = str(row[2]).strip() if len(row) > 2 and row[2] else "0"
                balance_str = str(row[3]).strip() if len(row) > 3 and row[3] else None

                amount = self._parse_amount(amount_str)
                balance = self._parse_amount(balance_str) if balance_str else None

                if date and description:
                    transactions.append(Transaction(
                        date=date,
                        description=description,
                        amount=amount,
                        balance=balance,
                        raw_text=" | ".join(str(c) for c in row if c)
                    ))
            except (IndexError, ValueError):
                continue

        return transactions

    def _parse_text(self, text: str) -> list[Transaction]:
        """Parse transactions from plain text (fallback method)."""
        transactions = []
        lines = text.split("\n")

        # Pattern for typical transaction line
        # Date followed by description and amounts
        pattern = re.compile(
            r"(\d{1,2}[\s/-]\w{3,9}[\s/-]?\d{0,4})\s+"  # Date
            r"(.+?)\s+"  # Description
            r"(-?[\d\s,]+\.\d{2})"  # Amount
            r"(?:\s+(-?[\d\s,]+\.\d{2}))?"  # Optional balance
        )

        for line in lines:
            line = line.strip()
            match = pattern.match(line)
            if match:
                date_str, description, amount_str, balance_str = match.groups()

                date = self._normalize_date(date_str)
                amount = self._parse_amount(amount_str)
                balance = self._parse_amount(balance_str) if balance_str else None

                if date and description:
                    transactions.append(Transaction(
                        date=date,
                        description=description.strip(),
                        amount=amount,
                        balance=balance,
                        raw_text=line
                    ))

        return transactions

    def _find_column(self, headers: list[str], keywords: list[str]) -> int | None:
        """Find column index matching any of the keywords."""
        for i, header in enumerate(headers):
            for keyword in keywords:
                if keyword in header:
                    return i
        return None

    def _looks_like_date(self, text: str) -> bool:
        """Check if text looks like a date."""
        if not text:
            return False
        # Check for common date patterns
        patterns = [
            r"\d{1,2}[\s/-]\w{3,9}",  # 01 Jan or 01/Jan
            r"\d{1,2}[\s/-]\d{1,2}[\s/-]\d{2,4}",  # 01/01/2024
        ]
        return any(re.match(p, text, re.IGNORECASE) for p in patterns)

    def _parse_amount(self, amount_str: str) -> float:
        """Parse amount string to float, handling various formats."""
        if not amount_str:
            return 0.0

        # Remove currency symbols, spaces, and normalize
        cleaned = re.sub(r"[R$€£\s]", "", str(amount_str))
        # Handle negative indicators
        is_negative = False
        if cleaned.startswith("(") and cleaned.endswith(")"):
            is_negative = True
            cleaned = cleaned[1:-1]
        if cleaned.startswith("-"):
            is_negative = True
            cleaned = cleaned[1:]
        if "CR" in cleaned.upper():
            cleaned = re.sub(r"CR", "", cleaned, flags=re.IGNORECASE)
        if "DR" in cleaned.upper():
            is_negative = True
            cleaned = re.sub(r"DR", "", cleaned, flags=re.IGNORECASE)

        # Remove thousand separators (handle both , and space)
        cleaned = cleaned.replace(",", "").replace(" ", "")

        try:
            amount = float(cleaned)
            return -amount if is_negative else amount
        except ValueError:
            return 0.0
