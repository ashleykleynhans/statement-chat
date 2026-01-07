"""Tests for watcher module."""

import pytest
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from watchdog.events import FileCreatedEvent

from src.watcher import StatementHandler, StatementWatcher, import_existing
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
