"""Tests for FNB parser module."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.parsers.fnb import FNBParser
from src.parsers.base import Transaction, StatementData
from src.parsers import get_parser, list_available_parsers, register_parser


@pytest.fixture
def parser():
    """Create an FNB parser instance."""
    return FNBParser()


class TestFNBParserMeta:
    """Tests for parser metadata."""

    def test_bank_name(self, parser):
        """Test bank name is correct."""
        assert parser.bank_name() == "fnb"


class TestAccountNumberExtraction:
    """Tests for account number extraction."""

    def test_extract_account_number_format1(self, parser):
        """Test extracting account number format 1."""
        text = "Account Number : 59410028368"
        result = parser._extract_account_number(text)
        assert result == "59410028368"

    def test_extract_account_number_format2(self, parser):
        """Test extracting account number format 2."""
        text = "59410028368 2025/10/01 Balance"
        result = parser._extract_account_number(text)
        assert result == "59410028368"

    def test_extract_account_number_not_found(self, parser):
        """Test when account number not found."""
        text = "Some random text without account number"
        result = parser._extract_account_number(text)
        assert result is None


class TestStatementDateExtraction:
    """Tests for statement date extraction."""

    def test_extract_statement_date(self, parser):
        """Test extracting statement date."""
        text = "Statement Date : 1 November 2025"
        result = parser._extract_statement_date(text)
        assert result == "2025-11-01"

    def test_extract_statement_date_not_found(self, parser):
        """Test when statement date not found."""
        text = "Some random text"
        result = parser._extract_statement_date(text)
        assert result is None

    def test_extract_statement_number(self, parser):
        """Test extracting statement number."""
        text = "Tax Invoice/Statement Number : 269"
        result = parser._extract_statement_number(text)
        assert result == "269"

    def test_extract_statement_number_without_tax_invoice(self, parser):
        """Test extracting statement number without Tax Invoice prefix."""
        text = "Statement Number : 287"
        result = parser._extract_statement_number(text)
        assert result == "287"

    def test_extract_statement_number_not_found(self, parser):
        """Test when statement number not found."""
        text = "Some random text"
        result = parser._extract_statement_number(text)
        assert result is None


class TestDateNormalization:
    """Tests for date normalization."""

    def test_normalize_date_full_month(self, parser):
        """Test normalizing date with full month name."""
        result = parser._normalize_date("15 January 2025")
        assert result == "2025-01-15"

    def test_normalize_date_short_month(self, parser):
        """Test normalizing date with short month name."""
        result = parser._normalize_date("15 Jan 2025")
        assert result == "2025-01-15"

    def test_normalize_date_slashes(self, parser):
        """Test normalizing date with slashes."""
        result = parser._normalize_date("15/01/2025")
        assert result == "2025-01-15"

    def test_normalize_date_invalid(self, parser):
        """Test normalizing invalid date returns original."""
        result = parser._normalize_date("invalid date")
        assert result == "invalid date"


class TestTransactionLineParsing:
    """Tests for transaction line parsing."""

    def test_parse_debit_transaction(self, parser):
        """Test parsing a debit transaction."""
        line = "02 Oct Internet Pmt To Keanu 720.00 18,196.65Cr"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.date == "2025-10-02"
        assert result.description == "Internet Pmt To Keanu"
        assert result.amount == -720.00
        assert result.balance == 18196.65

    def test_parse_credit_transaction(self, parser):
        """Test parsing a credit transaction."""
        line = "06 Oct FNB App Payment From Mom 5,200.00Cr 16,446.75Cr"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.date == "2025-10-06"
        assert result.description == "FNB App Payment From Mom"
        assert result.amount == 5200.00
        assert result.balance == 16446.75

    def test_parse_fee_line(self, parser):
        """Test parsing a fee line (no description, debit)."""
        line = "30 Sep 3.00 19,125.65Cr"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.date == "2025-09-30"
        assert result.description == "Bank fee/charge"
        assert result.amount == -3.00

    def test_parse_credit_line_no_description(self, parser):
        """Test parsing a credit line with no description."""
        line = "15 Oct 5,000.00Cr 25,000.00Cr"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.date == "2025-10-15"
        assert result.description == "Credit/Deposit"
        assert result.amount == 5000.00

    def test_parse_transaction_with_comma_amount(self, parser):
        """Test parsing transaction with comma in amount."""
        line = "15 Dec Payment To Someone 1,500.00 10,000.00Cr"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.amount == -1500.00

    def test_parse_transaction_with_three_amounts(self, parser):
        """Test parsing transaction with bank charges (3 amounts)."""
        line = "01 Jan Some Transaction 2,500.00 32,820.86Cr 3.30"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.amount == -2500.00
        assert result.balance == 32820.86

    def test_parse_invalid_line_no_date(self, parser):
        """Test parsing line without date returns None."""
        line = "Some random text without a date"
        result = parser._parse_transaction_line(line, 2025)
        assert result is None

    def test_parse_invalid_line_no_amount(self, parser):
        """Test parsing line without amount returns None."""
        line = "15 Oct Just a description"
        result = parser._parse_transaction_line(line, 2025)
        assert result is None

    def test_parse_dr_balance(self, parser):
        """Test parsing transaction with Dr (debit) balance."""
        line = "05 Nov Overdraft Fee 50.00 100.00Dr"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.balance == -100.00

    def test_parse_transaction_year_boundary(self, parser):
        """Test year adjustment for transactions crossing year boundary.

        A December transaction in a February statement should be previous year.
        """
        line = "29 Dec Bank fee/charge 5.00 1,000.00Cr"
        # Statement is February (month 2) of 2024
        result = parser._parse_transaction_line(line, 2024, statement_month=2)

        assert result is not None
        # Should be December 2023, not December 2024
        assert result.date == "2023-12-29"

    def test_parse_transaction_same_year(self, parser):
        """Test that nearby months don't get year adjusted."""
        line = "15 Jan Some Payment 100.00 5,000.00Cr"
        # Statement is February (month 2) of 2024
        result = parser._parse_transaction_line(line, 2024, statement_month=2)

        assert result is not None
        # January is close to February, should stay same year
        assert result.date == "2024-01-15"

    def test_parse_invalid_date_month(self, parser):
        """Test parsing transaction with invalid date returns None."""
        # Invalid month abbreviation should cause ValueError in strptime
        line = "32 Xyz Some Transaction 100.00 1000.00Cr"
        result = parser._parse_transaction_line(line, 2025)

        # No date match, returns None
        assert result is None

    def test_parse_invalid_day_causes_valueerror(self, parser):
        """Test parsing with invalid day number triggers ValueError branch."""
        # Day 31 in Feb doesn't exist, causing ValueError in strptime
        # The regex will match "31 Feb" but strptime will fail
        line = "31 Feb Some Transaction 100.00 1000.00Cr"
        result = parser._parse_transaction_line(line, 2025)

        # Should return None due to ValueError in date parsing
        assert result is None

    def test_parse_only_amounts_no_description(self, parser):
        """Test parsing line with amounts but description becomes empty after parsing."""
        # Line where description would be empty after amount extraction
        # This tests the "if not description: return None" at line 226
        line = "15 Oct 100.00"  # Only one amount, no balance, no description
        result = parser._parse_transaction_line(line, 2025)

        # With only one amount and no description, it should return None
        assert result is None


class TestTransactionsParsing:
    """Tests for full transactions parsing."""

    def test_parse_transactions_section(self, parser):
        """Test parsing transactions from statement text."""
        text = """
        Some header text
        Account Number: 12345678901

        Transactions in RAND
        Date Description Amount Balance
        01 Oct Opening Balance 0.00 10,000.00Cr
        02 Oct Woolworths Groceries 500.00 9,500.00Cr
        03 Oct Salary Credit 15,000.00Cr 24,500.00Cr

        *Indicates something
        """
        transactions = parser._parse_transactions(text)

        # Should parse the transactions (opening balance might be included)
        assert len(transactions) >= 2

    def test_parse_transactions_skips_headers(self, parser):
        """Test parsing skips header lines."""
        text = """
        Transactions in RAND
        Date Description Amount Balance
        01 Oct Test Transaction 100.00 1,000.00Cr
        """
        transactions = parser._parse_transactions(text)

        # Should only have 1 transaction, not the header
        for tx in transactions:
            assert "Description" not in tx.description

    def test_parse_transactions_abbreviated_month(self, parser):
        """Test parsing with abbreviated month name in statement date."""
        text = """
        Statement Date : 1 Feb 2024

        Transactions in RAND
        Date Description Amount Balance
        29 Dec Bank fee/charge 5.00 1,000.00Cr
        15 Jan Another payment 100.00 900.00Cr
        """
        transactions = parser._parse_transactions(text)

        assert len(transactions) == 2
        # December should be previous year (2023) due to year boundary
        assert transactions[0].date == "2023-12-29"
        # January should be same year (2024)
        assert transactions[1].date == "2024-01-15"

    def test_parse_transactions_invalid_month_in_statement(self, parser):
        """Test parsing with invalid month name falls back gracefully."""
        text = """
        Statement Date : 1 Xyz 2024

        Transactions in RAND
        Date Description Amount Balance
        15 Jan Test payment 100.00 900.00Cr
        """
        transactions = parser._parse_transactions(text)

        # Should still parse transactions, just without year boundary adjustment
        assert len(transactions) == 1
        assert transactions[0].date == "2024-01-15"

    def test_parse_transactions_no_space_in_header(self, parser):
        """Test parsing when PDF extracts text without spaces in header."""
        text = """
        Statement Date : 1 November 2025

        TransactionsinRAND(ZAR)
        Date Description Amount Balance
        15 Oct Some Payment 100.00 1,000.00Cr
        """
        transactions = parser._parse_transactions(text)

        assert len(transactions) == 1
        assert transactions[0].date == "2025-10-15"
        assert transactions[0].amount == -100.00

    def test_parse_transaction_no_space_between_day_and_month(self, parser):
        """Test parsing when PDF extracts date without space between day and month."""
        line = "02Jan POSPurchase Uber 124.33 14,149.25Cr"
        result = parser._parse_transaction_line(line, 2025)

        assert result is not None
        assert result.date == "2025-01-02"
        assert result.description == "POSPurchase Uber"
        assert result.amount == -124.33
        assert result.balance == 14149.25

    def test_parse_transactions_uses_statement_period_fallback(self, parser):
        """Test year extraction falls back to Statement Period when Statement Date is missing."""
        text = """
        Statement Period : 1 November 2025 to 1 December 2025

        Transactions in RAND
        Date Description Amount Balance
        15 Nov Some Payment 100.00 1,000.00Cr
        """
        transactions = parser._parse_transactions(text)

        assert len(transactions) == 1
        # Year should be 2025 from Statement Period's "to" date
        assert transactions[0].date == "2025-11-15"


class TestParseFile:
    """Tests for full PDF parsing."""

    def test_parse_nonexistent_file(self, parser):
        """Test parsing non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            parser.parse("/nonexistent/file.pdf")

    @patch('pdfplumber.open')
    def test_parse_pdf_file(self, mock_pdfplumber, parser):
        """Test parsing a PDF file."""
        # Mock PDF content
        mock_page = MagicMock()
        mock_page.extract_text.return_value = """
        Account Number : 59410028368
        Statement Date : 1 November 2025

        Transactions in RAND
        Date Description Amount Balance
        01 Oct Test Transaction 100.00 1,000.00Cr
        """
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)
        mock_pdfplumber.return_value = mock_pdf

        # Create a temp file path that "exists"
        with patch.object(Path, 'exists', return_value=True):
            result = parser.parse("test.pdf")

        assert isinstance(result, StatementData)
        assert result.account_number == "59410028368"
        assert result.statement_date == "2025-11-01"


class TestBaseBankParser:
    """Tests for base parser methods."""

    def test_determine_transaction_type_credit(self, parser):
        """Test credit type determination."""
        result = parser._determine_transaction_type(100.00)
        assert result == "credit"

    def test_determine_transaction_type_debit(self, parser):
        """Test debit type determination."""
        result = parser._determine_transaction_type(-100.00)
        assert result == "debit"

    def test_determine_transaction_type_zero(self, parser):
        """Test zero amount type determination."""
        result = parser._determine_transaction_type(0)
        assert result == "debit"


class TestOCRFallback:
    """Tests for OCR fallback functionality."""

    def test_fill_missing_descriptions_no_ocr_needed(self, parser, tmp_path):
        """Test that OCR is skipped when all descriptions are present."""
        transactions = [
            Transaction(date="2025-10-01", description="Real Description", amount=-100.0),
            Transaction(date="2025-10-02", description="Another Description", amount=-200.0),
        ]

        result = parser._fill_missing_descriptions_with_ocr(tmp_path / "test.pdf", transactions)

        # Should return unchanged since no generic descriptions
        assert result[0].description == "Real Description"
        assert result[1].description == "Another Description"

    @patch.object(FNBParser, '_extract_descriptions_via_ocr')
    def test_fill_missing_descriptions_with_ocr(self, mock_ocr, parser, tmp_path):
        """Test that OCR is used when generic descriptions are present."""
        mock_ocr.return_value = {
            ("10-01", -100.0): "#Service Fees #Test Fee",
        }

        transactions = [
            Transaction(date="2025-10-01", description="Bank fee/charge", amount=-100.0),
            Transaction(date="2025-10-02", description="Real Description", amount=-200.0),
        ]

        result = parser._fill_missing_descriptions_with_ocr(tmp_path / "test.pdf", transactions)

        assert result[0].description == "#Service Fees #Test Fee"
        assert result[1].description == "Real Description"

    @patch.object(FNBParser, '_extract_descriptions_via_ocr')
    def test_fill_missing_credit_deposit(self, mock_ocr, parser, tmp_path):
        """Test OCR fills Credit/Deposit descriptions."""
        mock_ocr.return_value = {
            ("09-30", 19.0): "#Rev Ewa Man Fee",
        }

        transactions = [
            Transaction(date="2025-09-30", description="Credit/Deposit", amount=19.0),
        ]

        result = parser._fill_missing_descriptions_with_ocr(tmp_path / "test.pdf", transactions)

        assert result[0].description == "#Rev Ewa Man Fee"

    @patch.object(FNBParser, '_extract_descriptions_via_ocr')
    def test_fill_missing_no_match_in_ocr(self, mock_ocr, parser, tmp_path):
        """Test description unchanged when no OCR match found."""
        mock_ocr.return_value = {}  # No OCR results

        transactions = [
            Transaction(date="2025-10-01", description="Bank fee/charge", amount=-100.0),
        ]

        result = parser._fill_missing_descriptions_with_ocr(tmp_path / "test.pdf", transactions)

        # Should keep original description
        assert result[0].description == "Bank fee/charge"

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_via_ocr_success(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR extraction parses transaction lines correctly."""
        # Mock OCR output
        mock_tesseract.image_to_string.return_value = """
        Some header text
        30 Sep |#Service Fees #Int Pymt Fee 3.00 19,125.65Cr
        30 Sep |#Rev Ewa Man Fee 19.00Cr 19,144.65Cr
        01 Oct |Regular Transaction 100.00 19,000.00Cr
        """

        # Mock fitz page rendering
        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100  # Minimal PNG header
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        # Mock PIL Image
        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_image.return_value = MagicMock()

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf")

        # Should have extracted descriptions
        assert ("09-30", -3.0) in result
        assert result[("09-30", -3.0)] == "#Service Fees #Int Pymt Fee"
        assert ("09-30", 19.0) in result
        assert result[("09-30", 19.0)] == "#Rev Ewa Man Fee"

    @patch('src.parsers.fnb.fitz')
    def test_extract_descriptions_via_ocr_handles_error(self, mock_fitz, parser, tmp_path):
        """Test OCR extraction handles errors gracefully."""
        mock_fitz.open.side_effect = Exception("PDF error")

        result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf")

        # Should return empty dict on error
        assert result == {}

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_ocr_credit_variations(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR handles various credit indicator formats (Cr, ¢7, etc.)."""
        # Mock OCR output with OCR errors in Cr (realistic OCR mangles balance too)
        # Note: No leading whitespace - re.match() requires pattern at start of line
        mock_tesseract.image_to_string.return_value = "I30 Sep |#Rev Ewa Man Fee 19.00¢7 19144.65\n"

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_image.return_value = MagicMock()

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf")

        # Should have parsed the credit despite OCR errors
        assert ("09-30", 19.0) in result

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_skips_empty_description(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR skips lines with empty descriptions."""
        mock_tesseract.image_to_string.return_value = """
        30 Sep |  100.00 19,000.00Cr
        """

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_image.return_value = MagicMock()

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf")

        # Empty description should be skipped
        assert len(result) == 0

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_invalid_date(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR skips lines with invalid dates (ValueError in strptime)."""
        # 31 Feb is invalid - regex matches but strptime fails with ValueError
        mock_tesseract.image_to_string.return_value = "31 Feb |Some Transaction 100.00 19,000.00Cr\n"

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_image.return_value = MagicMock()

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf")

        # Invalid date (31 Feb doesn't exist) should be skipped
        assert len(result) == 0

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_invalid_amount(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR skips lines when amount parsing fails (ValueError in float).

        This tests defensive code - the regex ensures valid digits, but we mock
        float() to simulate edge cases where parsing might fail.
        """
        mock_tesseract.image_to_string.return_value = "30 Sep |Some Transaction 100.00 19,000.00Cr\n"

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        # Mock float to raise ValueError for amount parsing (defensive code test)
        original_float = float

        def mock_float(x):
            # Only fail on the transaction amount, not on other floats
            if x == "100.00":
                raise ValueError("mocked float error")
            return original_float(x)

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_image.return_value = MagicMock()

            with patch('builtins.float', side_effect=mock_float):
                result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf")

        # Invalid amount should be skipped
        assert len(result) == 0

    def test_fill_missing_handles_none_date(self, parser, tmp_path):
        """Test fill_missing handles transactions with None date."""
        transactions = [
            Transaction(date=None, description="Credit/Deposit", amount=100.0),
        ]

        # Should not crash on None date
        with patch.object(parser, '_extract_descriptions_via_ocr', return_value={}):
            result = parser._fill_missing_descriptions_with_ocr(tmp_path / "test.pdf", transactions)

        assert result[0].description == "Credit/Deposit"

    @patch.object(FNBParser, '_extract_descriptions_via_ocr')
    def test_fill_missing_year_extraction_from_statement_date(self, mock_ocr, parser, tmp_path):
        """Test year extraction from statement_date (lines 152-154)."""
        mock_ocr.return_value = {}

        transactions = [
            Transaction(date="2025-10-01", description="Bank fee/charge", amount=-100.0),
        ]

        # With valid statement_date, year should be extracted
        result = parser._fill_missing_descriptions_with_ocr(
            tmp_path / "test.pdf", transactions, statement_date="2025-11-01"
        )

        # OCR should have been called with year=2025
        mock_ocr.assert_called_once()
        call_args = mock_ocr.call_args
        assert call_args[0][1] == 2025  # year argument

    @patch.object(FNBParser, '_extract_descriptions_via_ocr')
    def test_fill_missing_year_extraction_invalid_date(self, mock_ocr, parser, tmp_path):
        """Test year extraction handles invalid statement_date (ValueError branch, lines 152-154)."""
        mock_ocr.return_value = {}

        transactions = [
            Transaction(date="2025-10-01", description="Bank fee/charge", amount=-100.0),
        ]

        # With invalid statement_date, year extraction should fail gracefully
        result = parser._fill_missing_descriptions_with_ocr(
            tmp_path / "test.pdf", transactions, statement_date="invalid-date"
        )

        # OCR should have been called with year=None (fallback to current year internally)
        mock_ocr.assert_called_once()
        call_args = mock_ocr.call_args
        assert call_args[0][1] is None  # year argument should be None

    @patch.object(FNBParser, '_extract_descriptions_via_ocr')
    def test_fill_missing_year_extraction_type_error(self, mock_ocr, parser, tmp_path):
        """Test year extraction handles TypeError (lines 152-154)."""
        mock_ocr.return_value = {}

        transactions = [
            Transaction(date="2025-10-01", description="Bank fee/charge", amount=-100.0),
        ]

        # With None statement_date (TypeError on slicing)
        result = parser._fill_missing_descriptions_with_ocr(
            tmp_path / "test.pdf", transactions, statement_date=None
        )

        # Should not crash, OCR should be called with year=None
        mock_ocr.assert_called_once()

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_standalone_hash_description(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR extracts standalone # description lines (lines 222-223)."""
        # Mock OCR output with standalone # description followed by transaction without description
        mock_tesseract.image_to_string.return_value = (
            "#Monthly Account Fee\n"
            "01 Dec 120.00 3660.06\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2025)

        # Should have associated standalone description with the transaction
        assert ("12-01", -120.0) in result
        assert result[("12-01", -120.0)] == "#Monthly Account Fee"

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_inline_hash_description(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR extracts inline # descriptions (hash_match pattern, line 237-251)."""
        # Mock OCR output with inline # description
        mock_tesseract.image_to_string.return_value = (
            "01 Dec #Monthly Account Fee 120.00 3660.06\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2025)

        # Should have extracted inline # description
        assert ("12-01", -120.0) in result
        assert "#Monthly Account Fee" in result[("12-01", -120.0)]

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_hash_match_invalid_date(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR handles invalid date in hash_match (ValueError branch, line 250)."""
        # Invalid date (31 Feb doesn't exist) should be skipped
        mock_tesseract.image_to_string.return_value = (
            "31 Feb #Invalid Date Fee 100.00 1000.00\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2025)

        # Invalid date should be skipped
        assert len(result) == 0

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_standalone_with_transaction_below(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR matches standalone # description with transaction below (lines 290-312)."""
        # Standalone description on line 0, transaction without description on line 1
        mock_tesseract.image_to_string.return_value = (
            "#Value Added Serv Fees\n"
            "01 Dec 45.00 3615.06\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2025)

        # Should have matched standalone description with the transaction
        assert ("12-01", -45.0) in result
        assert result[("12-01", -45.0)] == "#Value Added Serv Fees"

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_no_standalone_for_transaction(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR transaction without description and no standalone above (lines 300-301)."""
        # Transaction without description and no standalone description above it
        mock_tesseract.image_to_string.return_value = (
            "01 Dec 120.00 3660.06\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2025)

        # No description should be added since there's no standalone above
        assert len(result) == 0

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_standalone_invalid_date_in_bare_tx(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR handles invalid date in bare transaction match (lines 302-311)."""
        # Standalone description followed by transaction with invalid date
        mock_tesseract.image_to_string.return_value = (
            "#Monthly Fee\n"
            "31 Feb 100.00 1000.00\n"  # Invalid date
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2025)

        # Invalid date should cause the transaction to be skipped
        assert len(result) == 0

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_multiple_standalone_uses_closest(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR uses closest preceding standalone description (lines 295-298)."""
        # Multiple standalone descriptions, should use the closest one above
        mock_tesseract.image_to_string.return_value = (
            "#First Description\n"
            "#Second Description\n"
            "01 Dec 100.00 1000.00\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2025)

        # Should use the closest standalone description (Second Description)
        assert ("12-01", -100.0) in result
        assert result[("12-01", -100.0)] == "#Second Description"

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_strips_slash_artifact(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR strips leading slash from # descriptions (OCR artifact)."""
        # OCR sometimes produces /# instead of #
        mock_tesseract.image_to_string.return_value = (
            "/#Service Fees\n"
            "01 Jul 39.70 1000.00\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2024)

        # Should have stripped the leading slash
        assert ("07-01", -39.70) in result
        assert result[("07-01", -39.70)] == "#Service Fees"
        assert "/" not in result[("07-01", -39.70)]

    @patch('src.parsers.fnb.fitz')
    @patch('src.parsers.fnb.pytesseract')
    def test_extract_descriptions_inline_strips_slash_artifact(self, mock_tesseract, mock_fitz, parser, tmp_path):
        """Test OCR strips leading slash from inline # descriptions."""
        # OCR sometimes produces /# instead of # in inline descriptions
        mock_tesseract.image_to_string.return_value = (
            "01 Jul /#Service Fees 39.70 1000.00\n"
        )

        mock_page = MagicMock()
        mock_pix = MagicMock()
        mock_pix.tobytes.return_value = b'\x89PNG\r\n\x1a\n' + b'\x00' * 100
        mock_page.get_pixmap.return_value = mock_pix

        mock_doc = MagicMock()
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc
        mock_fitz.Matrix.return_value = MagicMock()

        with patch('src.parsers.fnb.Image.open') as mock_image:
            mock_img = MagicMock()
            mock_img.convert.return_value = mock_img
            mock_image.return_value = mock_img

            result = parser._extract_descriptions_via_ocr(tmp_path / "test.pdf", year=2024)

        # Should have stripped the leading slash
        assert ("07-01", -39.70) in result
        assert result[("07-01", -39.70)] == "#Service Fees"
        assert "/" not in result[("07-01", -39.70)]


class TestParserRegistry:
    """Tests for parser registry functions."""

    def test_get_parser_fnb(self):
        """Test getting FNB parser."""
        parser = get_parser("fnb")
        assert parser.bank_name() == "fnb"

    def test_get_parser_invalid(self):
        """Test getting invalid parser raises error."""
        with pytest.raises(ValueError) as exc:
            get_parser("nonexistent_bank")

        assert "No parser available" in str(exc.value)
        assert "nonexistent_bank" in str(exc.value)

    def test_list_available_parsers(self):
        """Test listing available parsers."""
        parsers = list_available_parsers()
        assert "fnb" in parsers
        assert isinstance(parsers, list)
