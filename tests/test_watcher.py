"""Tests for watcher module."""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from watchdog.events import FileCreatedEvent

from rich.console import Console as RichConsole
from src.watcher import StatementHandler, StatementWatcher, import_existing, reimport_statement, _classify_and_prepare
from src.parsers.base import StatementData, Transaction
from src.classifier import ClassificationResult


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = Mock()
    db.statement_exists.return_value = False
    db.insert_statement.return_value = 1
    return db


@pytest.fixture
def mock_classifier():
    """Create a mock classifier."""
    classifier = Mock()
    classifier.classify.return_value = ClassificationResult(
        category="other",
        recipient_or_payer=None,
        confidence="high"
    )
    classifier.classify_rules_only.return_value = ClassificationResult(
        category="other",
        recipient_or_payer=None,
        confidence="high"
    )
    return classifier


@pytest.fixture
def mock_console():
    """Create a mock console."""
    return Mock()


class TestStatementHandler:
    """Tests for StatementHandler class."""

    def test_init(self, mock_db, mock_classifier):
        """Test handler initialization."""
        with patch('src.watcher.get_parser'):
            handler = StatementHandler(mock_db, "fnb", mock_classifier)

            assert handler.db == mock_db
            assert handler.bank == "fnb"
            assert handler.classifier == mock_classifier

    def test_on_created_ignores_directories(self, mock_db, mock_classifier):
        """Test handler ignores directory events."""
        with patch('src.watcher.get_parser'):
            handler = StatementHandler(mock_db, "fnb", mock_classifier)

            event = Mock()
            event.is_directory = True

            handler.on_created(event)

            mock_db.statement_exists.assert_not_called()

    def test_on_created_ignores_non_pdf(self, mock_db, mock_classifier):
        """Test handler ignores non-PDF files."""
        with patch('src.watcher.get_parser'):
            handler = StatementHandler(mock_db, "fnb", mock_classifier)

            event = Mock()
            event.is_directory = False
            event.src_path = "/path/to/file.txt"

            handler.on_created(event)

            mock_db.statement_exists.assert_not_called()

    @patch('src.watcher.time.sleep')
    def test_on_created_processes_pdf(self, mock_sleep, mock_db, mock_classifier, tmp_path):
        """Test handler processes PDF files."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[
                Transaction(
                    date="2025-01-15",
                    description="Test",
                    amount=-100.00,
                    balance=1000.00,
                )
            ]
        )

        with patch('src.watcher.get_parser', return_value=mock_parser):
            handler = StatementHandler(mock_db, "fnb", mock_classifier)

            pdf_path = tmp_path / "test.pdf"
            pdf_path.touch()

            event = Mock()
            event.is_directory = False
            event.src_path = str(pdf_path)

            handler.on_created(event)

            mock_db.insert_statement.assert_called_once()
            mock_db.insert_transactions_batch.assert_called_once()

    def test_process_file_skips_existing(self, mock_db, mock_classifier, tmp_path):
        """Test handler skips already imported files."""
        mock_db.statement_exists.return_value = True

        with patch('src.watcher.get_parser'):
            handler = StatementHandler(mock_db, "fnb", mock_classifier)

            pdf_path = tmp_path / "test.pdf"
            pdf_path.touch()

            handler._process_file(pdf_path)

            mock_db.insert_statement.assert_not_called()

    def test_process_file_handles_error(self, mock_db, mock_classifier, tmp_path):
        """Test handler handles parsing errors."""
        mock_parser = Mock()
        mock_parser.parse.side_effect = Exception("Parse error")

        with patch('src.watcher.get_parser', return_value=mock_parser):
            handler = StatementHandler(mock_db, "fnb", mock_classifier)

            pdf_path = tmp_path / "test.pdf"
            pdf_path.touch()

            # Should not raise, just log error
            handler._process_file(pdf_path)

            mock_db.insert_statement.assert_not_called()

    def test_process_file_credit_transaction(self, mock_db, mock_classifier, tmp_path):
        """Test handler correctly identifies credit transactions."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[
                Transaction(
                    date="2025-01-15",
                    description="Salary",
                    amount=10000.00,  # Positive = credit
                    balance=11000.00,
                )
            ]
        )

        with patch('src.watcher.get_parser', return_value=mock_parser):
            handler = StatementHandler(mock_db, "fnb", mock_classifier)

            pdf_path = tmp_path / "test.pdf"
            pdf_path.touch()

            handler._process_file(pdf_path)

            # Check the transaction was inserted with correct type
            call_args = mock_db.insert_transactions_batch.call_args[0]
            transactions = call_args[1]
            assert transactions[0]["transaction_type"] == "credit"


class TestStatementWatcher:
    """Tests for StatementWatcher class."""

    def test_init(self, mock_db, mock_classifier, tmp_path):
        """Test watcher initialization."""
        watcher = StatementWatcher(
            statements_dir=tmp_path,
            db=mock_db,
            bank="fnb",
            classifier=mock_classifier
        )

        assert watcher.statements_dir == tmp_path
        assert watcher.db == mock_db
        assert watcher.bank == "fnb"

    def test_start_creates_directory(self, mock_db, mock_classifier, tmp_path):
        """Test watcher creates directory if not exists."""
        watch_dir = tmp_path / "new_dir"

        watcher = StatementWatcher(
            statements_dir=watch_dir,
            db=mock_db,
            bank="fnb",
            classifier=mock_classifier
        )

        with patch('src.watcher.Observer') as mock_observer:
            with patch('src.watcher.get_parser'):
                # Make start return immediately by raising KeyboardInterrupt
                mock_observer.return_value.start.side_effect = KeyboardInterrupt()

                try:
                    watcher.start()
                except KeyboardInterrupt:
                    pass

        assert watch_dir.exists()

    @patch('src.watcher.Observer')
    @patch('src.watcher.get_parser')
    @patch('src.watcher.time.sleep')
    def test_start_and_stop(self, mock_sleep, mock_parser, mock_observer, mock_db, mock_classifier, tmp_path):
        """Test watcher start and stop."""
        watcher = StatementWatcher(
            statements_dir=tmp_path,
            db=mock_db,
            bank="fnb",
            classifier=mock_classifier
        )

        # Make sleep raise KeyboardInterrupt to exit loop
        mock_sleep.side_effect = KeyboardInterrupt()

        watcher.start()

        mock_observer.return_value.start.assert_called_once()
        mock_observer.return_value.stop.assert_called_once()
        mock_observer.return_value.join.assert_called_once()

    def test_stop_without_start(self, mock_db, mock_classifier, tmp_path):
        """Test stop when not started."""
        watcher = StatementWatcher(
            statements_dir=tmp_path,
            db=mock_db,
            bank="fnb",
            classifier=mock_classifier
        )

        # Should not raise
        watcher.stop()


class TestImportExisting:
    """Tests for import_existing function."""

    def test_import_creates_directory(self, mock_db, mock_classifier, tmp_path):
        """Test import creates directory if not exists."""
        new_dir = tmp_path / "new_statements"

        with patch('src.watcher.get_parser'):
            count = import_existing(new_dir, mock_db, "fnb", mock_classifier)

        assert new_dir.exists()
        assert count == 0

    def test_import_no_pdf_files(self, mock_db, mock_classifier, tmp_path):
        """Test import with no PDF files."""
        with patch('src.watcher.get_parser'):
            count = import_existing(tmp_path, mock_db, "fnb", mock_classifier)

        assert count == 0

    def test_import_skips_existing(self, mock_db, mock_classifier, tmp_path):
        """Test import skips already imported files."""
        mock_db.statement_exists.return_value = True

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser'):
            count = import_existing(tmp_path, mock_db, "fnb", mock_classifier)

        assert count == 0

    def test_import_processes_pdf(self, mock_db, mock_classifier, tmp_path):
        """Test import processes PDF files."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[
                Transaction(
                    date="2025-01-15",
                    description="Test",
                    amount=-100.00,
                    balance=1000.00,
                )
            ]
        )

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            count = import_existing(tmp_path, mock_db, "fnb", mock_classifier)

        assert count == 1
        mock_db.insert_statement.assert_called_once()
        mock_db.insert_transactions_batch.assert_called_once()

    def test_import_handles_error(self, mock_db, mock_classifier, tmp_path):
        """Test import handles parsing errors."""
        mock_parser = Mock()
        mock_parser.parse.side_effect = Exception("Parse error")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            count = import_existing(tmp_path, mock_db, "fnb", mock_classifier)

        assert count == 0

    def test_import_uppercase_pdf(self, mock_db, mock_classifier, tmp_path):
        """Test import handles uppercase .PDF extension."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[]
        )

        pdf_file = tmp_path / "test.PDF"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            count = import_existing(tmp_path, mock_db, "fnb", mock_classifier)

        assert count == 1

    def test_import_credit_transaction(self, mock_db, mock_classifier, tmp_path):
        """Test import correctly identifies credit transactions."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[
                Transaction(
                    date="2025-01-15",
                    description="Salary",
                    amount=10000.00,  # Positive = credit
                    balance=11000.00,
                )
            ]
        )

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            import_existing(tmp_path, mock_db, "fnb", mock_classifier)

        # Check the transaction was inserted with correct type
        call_args = mock_db.insert_transactions_batch.call_args[0]
        transactions = call_args[1]
        assert transactions[0]["transaction_type"] == "credit"

    def test_import_sorts_by_statement_number(self, mock_db, mock_classifier, tmp_path):
        """Test import processes files in statement number order."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[]
        )

        # Create files out of order
        (tmp_path / "287_Oct_2025.pdf").touch()
        (tmp_path / "262_Sep_2023.pdf").touch()
        (tmp_path / "290_Jan_2026.pdf").touch()
        (tmp_path / "old_format.pdf").touch()  # Non-matching format

        processed_files = []

        def track_statement(filename, **kwargs):
            processed_files.append(filename)
            return 1

        mock_db.insert_statement.side_effect = track_statement

        with patch('src.watcher.get_parser', return_value=mock_parser):
            import_existing(tmp_path, mock_db, "fnb", mock_classifier)

        # Files should be processed in statement number order, non-matching last
        assert processed_files == [
            "262_Sep_2023.pdf",
            "287_Oct_2025.pdf",
            "290_Jan_2026.pdf",
            "old_format.pdf",
        ]


class TestReimportStatement:
    """Tests for reimport_statement function."""

    def test_reimport_file_not_found(self, mock_db, mock_classifier, tmp_path):
        """Test reimport returns False for non-existent file."""
        result = reimport_statement(
            tmp_path / "nonexistent.pdf",
            mock_db,
            "fnb",
            mock_classifier
        )

        assert result is False

    def test_reimport_deletes_existing_first(self, mock_db, mock_classifier, tmp_path):
        """Test reimport deletes existing statement before re-importing."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[]
        )
        mock_db.delete_statement_by_filename.return_value = True

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            result = reimport_statement(pdf_file, mock_db, "fnb", mock_classifier)

        assert result is True
        mock_db.delete_statement_by_filename.assert_called_once_with("test.pdf")
        mock_db.insert_statement.assert_called_once()

    def test_reimport_new_file(self, mock_db, mock_classifier, tmp_path):
        """Test reimport works for file not previously imported."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[
                Transaction(
                    date="2025-01-15",
                    description="Test",
                    amount=-100.00,
                    balance=1000.00,
                )
            ]
        )
        mock_db.delete_statement_by_filename.return_value = False  # Not found

        pdf_file = tmp_path / "new.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            result = reimport_statement(pdf_file, mock_db, "fnb", mock_classifier)

        assert result is True
        mock_db.insert_statement.assert_called_once()
        mock_db.insert_transactions_batch.assert_called_once()

    def test_reimport_handles_parse_error(self, mock_db, mock_classifier, tmp_path):
        """Test reimport returns False on parse error."""
        mock_parser = Mock()
        mock_parser.parse.side_effect = Exception("Parse error")
        mock_db.delete_statement_by_filename.return_value = False

        pdf_file = tmp_path / "bad.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            result = reimport_statement(pdf_file, mock_db, "fnb", mock_classifier)

        assert result is False

    def test_reimport_classifies_transactions(self, mock_db, mock_classifier, tmp_path):
        """Test reimport classifies all transactions."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[
                Transaction(date="2025-01-15", description="Groceries", amount=-100.00),
                Transaction(date="2025-01-16", description="Salary", amount=5000.00),
            ]
        )
        mock_db.delete_statement_by_filename.return_value = False

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            reimport_statement(pdf_file, mock_db, "fnb", mock_classifier)

        # Classifier should be called for each transaction (rules first)
        assert mock_classifier.classify_rules_only.call_count == 2

    def test_reimport_credit_transaction(self, mock_db, mock_classifier, tmp_path):
        """Test reimport correctly identifies credit transactions."""
        mock_parser = Mock()
        mock_parser.parse.return_value = StatementData(
            account_number="123",
            statement_date="2025-01-01",
            transactions=[
                Transaction(
                    date="2025-01-15",
                    description="Salary",
                    amount=10000.00,  # Positive = credit
                    balance=11000.00,
                )
            ]
        )
        mock_db.delete_statement_by_filename.return_value = False

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch('src.watcher.get_parser', return_value=mock_parser):
            reimport_statement(pdf_file, mock_db, "fnb", mock_classifier)

        # Check the transaction was inserted with correct type
        call_args = mock_db.insert_transactions_batch.call_args[0]
        transactions = call_args[1]
        assert transactions[0]["transaction_type"] == "credit"


class TestClassifyAndPrepare:
    """Tests for _classify_and_prepare helper."""

    def test_all_matched_by_rules(self, mock_classifier):
        """Test when all transactions match rules (no LLM calls)."""
        console = Mock()
        txs = [
            Transaction(date="2025-01-01", description="Groceries", amount=-100.00),
            Transaction(date="2025-01-02", description="Salary", amount=5000.00),
        ]

        results = _classify_and_prepare(txs, mock_classifier, console)

        assert len(results) == 2
        assert results[0]["category"] == "other"
        assert results[1]["transaction_type"] == "credit"
        mock_classifier.classify_batch_llm.assert_not_called()

    def test_llm_fallback_for_unmatched(self, mock_classifier):
        """Test LLM is called for transactions not matched by rules."""
        console = RichConsole(quiet=True)
        mock_classifier.classify_rules_only.side_effect = [
            ClassificationResult(category="groceries", recipient_or_payer=None, confidence="high"),
            None,  # No rule match
        ]
        mock_classifier.classify_batch_llm.return_value = [
            ClassificationResult(category="fuel", recipient_or_payer="Shell", confidence="medium"),
        ]

        txs = [
            Transaction(date="2025-01-01", description="Woolworths", amount=-100.00),
            Transaction(date="2025-01-02", description="Unknown Station", amount=-200.00),
        ]

        results = _classify_and_prepare(txs, mock_classifier, console)

        assert len(results) == 2
        assert results[0]["category"] == "groceries"
        assert results[1]["category"] == "fuel"
        assert results[1]["recipient_or_payer"] == "Shell"
        mock_classifier.classify_batch_llm.assert_called_once()

    def test_all_need_llm(self, mock_classifier):
        """Test when no transactions match rules."""
        console = RichConsole(quiet=True)
        mock_classifier.classify_rules_only.return_value = None
        mock_classifier.classify_batch_llm.return_value = [
            ClassificationResult(category="other", recipient_or_payer=None, confidence="low"),
            ClassificationResult(category="other", recipient_or_payer=None, confidence="low"),
        ]

        txs = [
            Transaction(date="2025-01-01", description="Unknown1", amount=-100.00),
            Transaction(date="2025-01-02", description="Unknown2", amount=-200.00),
        ]

        results = _classify_and_prepare(txs, mock_classifier, console)

        assert len(results) == 2
        assert all(r["category"] == "other" for r in results)

    def test_debit_and_credit_types(self, mock_classifier):
        """Test transaction types are set correctly."""
        console = Mock()
        txs = [
            Transaction(date="2025-01-01", description="Purchase", amount=-100.00),
            Transaction(date="2025-01-02", description="Deposit", amount=500.00),
        ]

        results = _classify_and_prepare(txs, mock_classifier, console)

        assert results[0]["transaction_type"] == "debit"
        assert results[0]["amount"] == 100.00
        assert results[1]["transaction_type"] == "credit"
        assert results[1]["amount"] == 500.00
