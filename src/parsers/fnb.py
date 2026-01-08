"""FNB (First National Bank) statement parser."""

import re
from datetime import datetime
from pathlib import Path

import pdfplumber

from . import register_parser
from .base import BaseBankParser, StatementData, Transaction


@register_parser
class FNBParser(BaseBankParser):
    """Parser for FNB bank statements."""

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
        full_text = ""

        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                full_text += page_text + "\n"

        # Extract account number
        account_number = self._extract_account_number(full_text)

        # Extract statement date
        statement_date = self._extract_statement_date(full_text)

        # Extract statement number
        statement_number = self._extract_statement_number(full_text)

        # Parse transactions from text
        transactions = self._parse_transactions(full_text)

        return StatementData(
            account_number=account_number,
            statement_date=statement_date,
            statement_number=statement_number,
            transactions=transactions
        )

    def _extract_account_number(self, text: str) -> str | None:
        """Extract account number from statement text."""
        patterns = [
            r"Account\s*Number\s*[\s:]*(\d{10,})",
            r"(\d{11})\s+\d{4}/\d{2}/\d{2}",  # FNB format: account date
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        return None

    def _extract_statement_date(self, text: str) -> str | None:
        """Extract statement date from text."""
        # Look for "Statement Date : 1 November 2025"
        match = re.search(
            r"Statement\s*Date\s*[:\s]+(\d{1,2}\s+\w+\s+\d{4})",
            text, re.IGNORECASE
        )
        if match:
            return self._normalize_date(match.group(1))
        return None

    def _extract_statement_number(self, text: str) -> str | None:
        """Extract statement number from text."""
        # Look for "Tax Invoice/Statement Number : 269" or "Statement Number : 269"
        match = re.search(
            r"(?:Tax\s*Invoice/)?Statement\s*Number\s*[:\s]+(\d+)",
            text, re.IGNORECASE
        )
        if match:
            return match.group(1)
        return None

    def _normalize_date(self, date_str: str) -> str | None:
        """Convert various date formats to YYYY-MM-DD."""
        date_formats = [
            "%d %B %Y",
            "%d %b %Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
        ]

        date_str = date_str.strip()

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    def _parse_transactions(self, text: str) -> list[Transaction]:
        """Parse transactions from FNB statement text."""
        transactions = []

        # FNB transaction line pattern:
        # DD Mon Description Amount Balance [BankCharges]
        # Amount can be like: 720.00 or 5,200.00Cr
        # Balance is like: 18,196.65Cr or 4,416.75Dr

        # Split into lines
        lines = text.split("\n")

        # Find the transactions section (after "Transactions in RAND")
        in_transactions = False
        current_year = None

        # Extract year and month from Statement Date (not Statement Period which may have different year)
        # Statement Date format: "Statement Date : 2 January 2026"
        statement_month = None
        current_year = None
        date_match = re.search(r"Statement\s*Date\s*[:\s]+(\d{1,2})\s+(\w+)\s+(\d{4})", text, re.IGNORECASE)
        if date_match:
            current_year = int(date_match.group(3))
            try:
                statement_month = datetime.strptime(date_match.group(2), "%B").month
            except ValueError:
                try:
                    statement_month = datetime.strptime(date_match.group(2), "%b").month
                except ValueError:
                    pass

        # Fallback: try Statement Period if Statement Date not found
        if current_year is None:
            year_match = re.search(r"Statement\s*Period.*?to.*?(\d{4})", text)
            if year_match:
                current_year = int(year_match.group(1))
            else:
                current_year = datetime.now().year

        for line in lines:
            line = line.strip()

            # Skip empty lines
            if not line:
                continue

            # Detect start of transactions section (handle with/without space)
            # Some PDFs extract text without spaces: "TransactionsinRAND"
            if ("Transactions in" in line or "Transactionsin" in line) and "RAND" in line:
                in_transactions = True
                continue

            # Skip header line
            if line.startswith("Date") and "Description" in line:
                continue

            if not in_transactions:
                continue

            # Stop at footer sections
            if any(x in line for x in ["*Indicates", "**Interest", "Important information", "Page "]):
                continue

            # Try to parse transaction line
            tx = self._parse_transaction_line(line, current_year, statement_month)
            if tx:
                transactions.append(tx)

        return transactions

    def _parse_transaction_line(self, line: str, year: int, statement_month: int | None = None) -> Transaction | None:
        """Parse a single transaction line."""
        # Pattern: DD Mon [Description] Amount Balance [BankCharges]
        # Examples:
        # "30 Sep 3.00 19,125.65Cr"
        # "02 Oct Internet Pmt To Keanu... 720.00 18,196.65Cr"
        # "06 Oct FNB App Payment From Mom 5,200.00Cr 16,446.75Cr"

        # Match date at start (whitespace between day and month is optional due to PDF extraction)
        date_match = re.match(r"^(\d{1,2})\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b", line, re.IGNORECASE)
        if not date_match:
            return None

        day = date_match.group(1)
        month = date_match.group(2)

        # Parse the date
        try:
            date_str = f"{day} {month} {year}"
            dt = datetime.strptime(date_str, "%d %b %Y")

            # Handle year boundary: if transaction month is much later than statement month,
            # it's likely from the previous year (e.g., Dec transaction in a Feb statement)
            if statement_month is not None:
                tx_month = dt.month
                # If transaction month is > 6 months after statement month, assume previous year
                # e.g., statement is Feb (2), transaction is Dec (12): 12 - 2 = 10 > 6
                if tx_month - statement_month > 6:
                    dt = dt.replace(year=year - 1)

            date = dt.strftime("%Y-%m-%d")
        except ValueError:
            return None

        # Rest of the line after date
        rest = line[date_match.end():].strip()

        # Find amounts at the end - looking for patterns like:
        # "720.00 18,196.65Cr" or "5,200.00Cr 16,446.75Cr" or "2,500.00 32,820.86Cr 3.30"
        # Amount pattern: digits with optional comma separators, decimal point, 2 digits, optional Cr/Dr
        amount_pattern = r"([\d,]+\.\d{2})(Cr|Dr)?"

        # Find all amounts in the line
        amounts = list(re.finditer(amount_pattern, rest))

        if len(amounts) < 1:
            return None

        # FNB format: Amount | Balance | [Bank Charges]
        # - First amount is the transaction amount
        # - Second amount (usually with Cr/Dr suffix) is the balance
        # - Third amount (if present) is bank charges (ignore)
        amount_match = amounts[0]  # First amount is always the transaction

        # Balance is the second amount if present
        balance_match = amounts[1] if len(amounts) >= 2 else None

        # Extract description (everything between date and first amount)
        desc_end = amounts[0].start() if amounts else len(rest)
        description = rest[:desc_end].strip()

        # If no description, determine based on transaction type
        if not description and len(amounts) >= 2:
            # Check if it's a credit or debit based on suffix
            first_amount_suffix = amount_match.group(2)
            if first_amount_suffix == "Cr":
                description = "Credit/Deposit"
            else:
                description = "Bank fee/charge"

        # Parse the amount
        amount_str = amount_match.group(1).replace(",", "")
        amount = float(amount_str)

        # Determine if credit or debit
        # Cr suffix = credit (money in), no suffix or Dr = debit (money out)
        amount_suffix = amount_match.group(2)
        if amount_suffix == "Cr":
            # Credit - positive amount
            pass
        else:
            # Debit - negative amount
            amount = -amount

        # Parse balance if present
        balance = None
        if balance_match:
            balance_str = balance_match.group(1).replace(",", "")
            balance = float(balance_str)
            if balance_match.group(2) == "Dr":
                balance = -balance

        if not description:
            return None

        return Transaction(
            date=date,
            description=description,
            amount=amount,
            balance=balance,
            reference=None,
            raw_text=line
        )
