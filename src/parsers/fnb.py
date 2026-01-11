"""FNB (First National Bank) statement parser."""

import io
import re
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image

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

                # Also try to extract tables for better column handling
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if row:
                            # Join non-empty cells with space
                            row_text = " ".join(str(cell) for cell in row if cell)
                            full_text += row_text + "\n"

        # Extract account number
        account_number = self._extract_account_number(full_text)

        # Extract statement date
        statement_date = self._extract_statement_date(full_text)

        # Extract statement number
        statement_number = self._extract_statement_number(full_text)

        # Parse transactions from text
        transactions = self._parse_transactions(full_text)

        # Use OCR to fill in missing descriptions (FNB uses special font for # descriptions)
        # Pass statement_date to determine the year for OCR date parsing
        transactions = self._fill_missing_descriptions_with_ocr(pdf_path, transactions, statement_date)

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
        # Look for "Statement Date : 1 November 2025" or "StatementDate:1November2025"
        match = re.search(
            r"Statement\s*Date\s*[:\s]+(\d{1,2}\s*\w+\s*\d{4})",
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
        date_str = date_str.strip()

        # Add spaces if missing (e.g., "1February2025" -> "1 February 2025")
        date_str = re.sub(r"(\d)([A-Za-z])", r"\1 \2", date_str)
        date_str = re.sub(r"([A-Za-z])(\d)", r"\1 \2", date_str)

        date_formats = [
            "%d %B %Y",
            "%d %b %Y",
            "%d/%m/%Y",
            "%Y/%m/%d",
        ]

        for fmt in date_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return date_str

    def _fill_missing_descriptions_with_ocr(
        self, pdf_path: Path, transactions: list[Transaction], statement_date: str | None = None
    ) -> list[Transaction]:
        """Use OCR to fill in descriptions that couldn't be extracted.

        FNB uses a special font for system-generated descriptions (starting with #)
        that PDF text extraction can't read. OCR can capture these.
        """
        # Check if any transactions need OCR (missing or generic descriptions)
        generic_descriptions = {"Credit/Deposit", "Bank fee/charge"}
        needs_ocr = any(
            tx.description in generic_descriptions
            for tx in transactions
        )

        if not needs_ocr:
            return transactions

        # Extract year from statement_date for OCR date parsing
        year = None
        if statement_date:
            try:
                year = int(statement_date[:4])
            except (ValueError, TypeError):
                pass

        # Extract descriptions via OCR
        ocr_descriptions = self._extract_descriptions_via_ocr(pdf_path, year)

        # Match OCR descriptions to transactions by month-day and amount
        updated_transactions = []
        for tx in transactions:
            if tx.description in generic_descriptions:
                # Try to find matching OCR description (using month-day, amount as key)
                month_day = tx.date[5:] if tx.date else ""  # Extract MM-DD
                key = (month_day, tx.amount)
                if key in ocr_descriptions:
                    tx = Transaction(
                        date=tx.date,
                        description=ocr_descriptions[key],
                        amount=tx.amount,
                        balance=tx.balance,
                        reference=tx.reference,
                        raw_text=tx.raw_text,
                    )
            updated_transactions.append(tx)

        return updated_transactions

    def _extract_descriptions_via_ocr(self, pdf_path: Path, year: int | None = None) -> dict[tuple, str]:
        """Extract transaction descriptions using OCR.

        Returns a dict mapping (date, amount) to description.
        """
        # Use provided year or current year as fallback
        if year is None:
            year = datetime.now().year
        descriptions = {}

        try:
            doc = fitz.open(pdf_path)
            for page_num, page in enumerate(doc):
                # Render page to image at 4x resolution for better OCR of small fonts
                mat = fitz.Matrix(4, 4)
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))

                # Convert to grayscale for better OCR
                img = img.convert("L")

                # Run OCR with custom config for better text detection
                # PSM 6: Assume uniform block of text (better for tables)
                # OEM 3: Default, based on what's available
                custom_config = r'--psm 6 --oem 3'
                ocr_text = pytesseract.image_to_string(img, config=custom_config)

                # Debug: print OCR output for inspection
                import logging
                logger = logging.getLogger(__name__)
                logger.debug(f"OCR Page {page_num + 1} output:\n{ocr_text[:2000]}")

                # First pass: collect standalone description lines (starting with #)
                # and transaction lines without descriptions
                ocr_lines = ocr_text.split("\n")
                standalone_descriptions = []

                for i, line in enumerate(ocr_lines):
                    # Check for standalone # description line (anywhere in the line)
                    # Handle OCR artifacts like /# instead of just #
                    desc_match = re.search(r"[/|\\]?#\s*([A-Za-z][A-Za-z0-9\s\-]+)", line)
                    if desc_match and not re.search(r"\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", line, re.IGNORECASE):
                        # Line has # description but no date - it's a standalone description
                        standalone_descriptions.append((i, "#" + desc_match.group(1).strip()))
                        continue

                # Parse OCR text for transaction lines
                for i, line in enumerate(ocr_lines):
                    # First, try to match lines with # descriptions inline
                    # Pattern: date | #description | amount | balance
                    # Handle OCR artifacts like /# instead of just #
                    hash_match = re.match(
                        r"[|\[I]?\s*(\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s*[|\s]+"
                        r"[/|\\]?(#[A-Za-z][^\d]*?)\s+"
                        r"([\d,]+\.\d{2})\s+"
                        r"[\d,]+[.,]\d+",
                        line,
                        re.IGNORECASE,
                    )
                    if hash_match:
                        date_str = hash_match.group(1).strip()
                        description = hash_match.group(2).strip()
                        # Clean up any remaining OCR artifacts from description
                        description = re.sub(r"^[/|\\]+", "", description)
                        amount_str = hash_match.group(3).strip()

                        try:
                            date_str = re.sub(r"(\d)([A-Za-z])", r"\1 \2", date_str)
                            dt = datetime.strptime(f"{date_str} {year}", "%d %b %Y")
                            date = dt.strftime("%Y-%m-%d")
                            amount_str_clean = amount_str.replace(",", "")
                            amount = -float(amount_str_clean)  # Fees are debits
                            month_day = date[5:]
                            descriptions[(month_day, amount)] = description
                        except (ValueError, TypeError):
                            pass
                        continue

                    # Look for transaction pattern: date | description | amount | balance
                    # OCR output format varies, look for date at start
                    # Handle OCR errors like "I30" instead of "30", "¢7" instead of "Cr"
                    match = re.match(
                        r"[|\[I]?\s*(\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s*[|\s]+"
                        r"(.+?)\s+"
                        r"([\d,]+\.\d{2}[Cc¢][r7|]*)\s*[|\s]*"  # Credit with OCR variations
                        r"[\d,]+[.,]\d+",
                        line,
                        re.IGNORECASE,
                    )
                    # Also try pattern for debits (no Cr suffix)
                    if not match:
                        match = re.match(
                            r"[|\[I]?\s*(\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s*[|\s]+"
                            r"(.+?)\s+"
                            r"([\d,]+\.\d{2})\s+[|\s]*"  # Debit (no suffix)
                            r"[\d,]+[.,]\d+",
                            line,
                            re.IGNORECASE,
                        )
                        is_debit_match = True
                    else:
                        is_debit_match = False

                    # Try pattern for transactions WITHOUT description (just date, amount, balance)
                    if not match:
                        match = re.match(
                            r"[|\[I]?\s*(\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec))\s+"
                            r"([\d,]+\.\d{2})\s+"
                            r"[\d,]+[.,]\d+",
                            line,
                            re.IGNORECASE,
                        )
                        if match:
                            # Transaction without inline description - try to find nearby # description
                            date_str = match.group(1).strip()
                            amount_str = match.group(2).strip()

                            # Look for closest standalone description above this line
                            description = None
                            for desc_line_num, desc_text in reversed(standalone_descriptions):
                                if desc_line_num < i:
                                    description = desc_text  # desc_text already has # prefix
                                    break

                            if description:
                                # Parse and store this transaction with the found description
                                try:
                                    date_str = re.sub(r"(\d)([A-Za-z])", r"\1 \2", date_str)
                                    dt = datetime.strptime(f"{date_str} {year}", "%d %b %Y")
                                    date = dt.strftime("%Y-%m-%d")
                                    amount_str_clean = amount_str.replace(",", "")
                                    amount = -float(amount_str_clean)  # Fees are debits
                                    month_day = date[5:]
                                    descriptions[(month_day, amount)] = description
                                except (ValueError, TypeError):
                                    pass
                            continue

                    if match:
                        date_str = match.group(1).strip()
                        description = match.group(2).strip()
                        amount_str = match.group(3).strip()

                        # Clean up description (remove OCR artifacts like |, [], {}, _)
                        description = re.sub(r"^[|\[\]{}_]+", "", description).strip()

                        # Skip if description is empty or just whitespace
                        if not description or description.isspace():
                            continue

                        # Parse date to standard format
                        try:
                            # Add spaces if missing
                            date_str = re.sub(r"(\d)([A-Za-z])", r"\1 \2", date_str)
                            dt = datetime.strptime(f"{date_str} {year}", "%d %b %Y")
                            date = dt.strftime("%Y-%m-%d")
                        except ValueError:
                            continue

                        # Parse amount - check for Cr/credit indicators (including OCR errors)
                        is_credit = bool(re.search(r"[Cc¢][r7|]", amount_str))
                        amount_str = re.sub(r"[Cc¢][r7|]+", "", amount_str).replace(",", "")
                        try:
                            amount = float(amount_str)
                            if is_credit:
                                amount = amount  # positive for credit
                            else:
                                amount = -amount  # negative for debit
                        except ValueError:
                            continue

                        # Store with date and amount as key
                        # Note: year in date might be wrong, we'll match by month/day + amount
                        month_day = date[5:]  # MM-DD
                        descriptions[(month_day, amount)] = description

            doc.close()
        except Exception:
            # If OCR fails, just return empty dict and use default descriptions
            pass

        return descriptions

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
