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
