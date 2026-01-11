"""Tests for main CLI module."""

import argparse
import sys
import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open
from io import StringIO

from src import main
from src.main import (
    cmd_import, cmd_watch, cmd_chat, cmd_list,
    cmd_categories, cmd_stats, cmd_search, cmd_parsers, cmd_rename, cmd_reimport, cmd_serve
)


@pytest.fixture
def mock_config():
    """Create a mock config."""
    return {
        "bank": "fnb",
        "ollama": {
            "host": "localhost",
            "port": 11434,
            "model": "llama3.2",
        },
        "paths": {
            "statements_dir": "./statements",
            "database": "./data/test.db",
        },
        "categories": ["groceries", "fuel"],
        "classification_rules": {},
    }


@pytest.fixture
def mock_args():
    """Create mock argparse namespace."""
    return argparse.Namespace(
        command="list",
        config="config.yaml",
        limit=None,
        term=None,
        path=None,
        bank=None,
    )


class TestCmdImport:
    """Tests for cmd_import function."""

    @patch('src.main.import_existing')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_import_success(self, mock_db, mock_classifier, mock_import, mock_config, mock_args):
        """Test successful import."""
        mock_classifier.return_value.check_connection.return_value = True
        mock_import.return_value = 5

        cmd_import(mock_args, mock_config)

        mock_import.assert_called_once()

    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_import_no_connection(self, mock_db, mock_classifier, mock_config, mock_args):
        """Test import fails when Ollama not connected."""
        mock_classifier.return_value.check_connection.return_value = False
        mock_classifier.return_value.get_available_models.return_value = []

        with pytest.raises(SystemExit) as exc:
            cmd_import(mock_args, mock_config)

        assert exc.value.code == 1

    @patch('src.main.import_existing')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_import_with_path_override(self, mock_db, mock_classifier, mock_import, mock_config):
        """Test import with --path override."""
        mock_classifier.return_value.check_connection.return_value = True
        mock_import.return_value = 3

        args = argparse.Namespace(path="/custom/path", bank=None)
        cmd_import(args, mock_config)

        # Should use custom path instead of config
        call_kwargs = mock_import.call_args.kwargs
        assert call_kwargs["statements_dir"] == "/custom/path"
        assert call_kwargs["bank"] == "fnb"  # Falls back to config

    @patch('src.main.import_existing')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_import_with_bank_override(self, mock_db, mock_classifier, mock_import, mock_config):
        """Test import with --bank override."""
        mock_classifier.return_value.check_connection.return_value = True
        mock_import.return_value = 2

        args = argparse.Namespace(path=None, bank="standardbank")
        cmd_import(args, mock_config)

        call_kwargs = mock_import.call_args.kwargs
        assert call_kwargs["statements_dir"] == "./statements"  # Falls back to config
        assert call_kwargs["bank"] == "standardbank"


class TestCmdWatch:
    """Tests for cmd_watch function."""

    @patch('src.main.StatementWatcher')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_watch_success(self, mock_db, mock_classifier, mock_watcher, mock_config, mock_args):
        """Test successful watch start."""
        mock_classifier.return_value.check_connection.return_value = True

        cmd_watch(mock_args, mock_config)

        mock_watcher.return_value.start.assert_called_once()

    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_watch_no_connection(self, mock_db, mock_classifier, mock_config, mock_args):
        """Test watch fails when Ollama not connected."""
        mock_classifier.return_value.check_connection.return_value = False

        with pytest.raises(SystemExit) as exc:
            cmd_watch(mock_args, mock_config)

        assert exc.value.code == 1


class TestCmdChat:
    """Tests for cmd_chat function."""

    @patch('src.main.ChatInterface')
    @patch('src.main.Database')
    def test_chat_success(self, mock_db, mock_chat, mock_config, mock_args):
        """Test successful chat start."""
        mock_db.return_value.get_stats.return_value = {"total_transactions": 10}

        cmd_chat(mock_args, mock_config)

        mock_chat.return_value.start.assert_called_once()

    @patch('src.main.Database')
    def test_chat_no_transactions(self, mock_db, mock_config, mock_args):
        """Test chat fails when no transactions."""
        mock_db.return_value.get_stats.return_value = {"total_transactions": 0}

        with pytest.raises(SystemExit) as exc:
            cmd_chat(mock_args, mock_config)

        assert exc.value.code == 1


class TestCmdList:
    """Tests for cmd_list function."""

    @patch('src.main.Database')
    def test_list_transactions(self, mock_db, mock_config, mock_args):
        """Test listing transactions."""
        mock_db.return_value.get_all_transactions.return_value = [
            {"date": "2025-01-15", "description": "Test", "amount": 100,
             "transaction_type": "debit", "category": "other"}
        ]

        cmd_list(mock_args, mock_config)

        mock_db.return_value.get_all_transactions.assert_called_once()

    @patch('src.main.Database')
    def test_list_with_limit(self, mock_db, mock_config):
        """Test listing with custom limit."""
        args = argparse.Namespace(limit=50)
        mock_db.return_value.get_all_transactions.return_value = []

        cmd_list(args, mock_config)

        mock_db.return_value.get_all_transactions.assert_called_with(limit=50)

    @patch('src.main.Database')
    def test_list_no_transactions(self, mock_db, mock_config, mock_args):
        """Test listing when no transactions."""
        mock_db.return_value.get_all_transactions.return_value = []

        # Should not raise, just print message
        cmd_list(mock_args, mock_config)

    @patch('src.main.Database')
    def test_list_credit_transaction(self, mock_db, mock_config, mock_args):
        """Test listing credit transactions shows green."""
        mock_db.return_value.get_all_transactions.return_value = [
            {"date": "2025-01-15", "description": "Salary", "amount": 10000,
             "transaction_type": "credit", "category": "salary"}
        ]

        cmd_list(mock_args, mock_config)


class TestCmdCategories:
    """Tests for cmd_categories function."""

    @patch('src.main.Database')
    def test_categories_summary(self, mock_db, mock_config, mock_args):
        """Test category summary display."""
        mock_db.return_value.get_category_summary.return_value = [
            {"category": "groceries", "count": 10, "total_debits": 500, "total_credits": 0},
            {"category": None, "count": 5, "total_debits": 100, "total_credits": 0},
        ]

        cmd_categories(mock_args, mock_config)

        mock_db.return_value.get_category_summary.assert_called_once()

    @patch('src.main.Database')
    def test_categories_empty(self, mock_db, mock_config, mock_args):
        """Test categories when empty."""
        mock_db.return_value.get_category_summary.return_value = []

        cmd_categories(mock_args, mock_config)


class TestCmdStats:
    """Tests for cmd_stats function."""

    @patch('src.main.Database')
    def test_stats_display(self, mock_db, mock_config, mock_args):
        """Test stats display."""
        mock_db.return_value.get_stats.return_value = {
            "total_statements": 3,
            "total_transactions": 100,
            "total_debits": 5000,
            "total_credits": 10000,
            "categories_count": 5,
        }

        cmd_stats(mock_args, mock_config)

        mock_db.return_value.get_stats.assert_called_once()


class TestCmdSearch:
    """Tests for cmd_search function."""

    @patch('src.main.Database')
    def test_search_found(self, mock_db, mock_config):
        """Test search with results."""
        args = argparse.Namespace(term="woolworths")
        mock_db.return_value.search_transactions.return_value = [
            {"date": "2025-01-15", "description": "Woolworths", "amount": 500,
             "transaction_type": "debit", "category": "groceries"}
        ]

        cmd_search(args, mock_config)

        mock_db.return_value.search_transactions.assert_called_with("woolworths")

    @patch('src.main.Database')
    def test_search_not_found(self, mock_db, mock_config):
        """Test search with no results."""
        args = argparse.Namespace(term="nonexistent")
        mock_db.return_value.search_transactions.return_value = []

        cmd_search(args, mock_config)

    @patch('src.main.Database')
    def test_search_credit_result(self, mock_db, mock_config):
        """Test search with credit transaction result."""
        args = argparse.Namespace(term="salary")
        mock_db.return_value.search_transactions.return_value = [
            {"date": "2025-01-15", "description": "Salary", "amount": 10000,
             "transaction_type": "credit", "category": "salary"}
        ]

        cmd_search(args, mock_config)


class TestCmdParsers:
    """Tests for cmd_parsers function."""

    @patch('src.main.list_available_parsers')
    def test_parsers_list(self, mock_list, mock_config, mock_args):
        """Test listing parsers."""
        mock_list.return_value = ["fnb", "standardbank"]

        cmd_parsers(mock_args, mock_config)

        mock_list.assert_called_once()

    @patch('src.main.list_available_parsers')
    def test_parsers_empty(self, mock_list, mock_config, mock_args):
        """Test listing when no parsers."""
        mock_list.return_value = []

        cmd_parsers(mock_args, mock_config)

    @patch('src.main.list_available_parsers')
    def test_parsers_shows_active(self, mock_list, mock_config, mock_args):
        """Test active parser is marked."""
        mock_list.return_value = ["fnb"]
        mock_config["bank"] = "fnb"

        cmd_parsers(mock_args, mock_config)


class TestMain:
    """Tests for main function."""

    @patch('src.main.get_config')
    @patch('src.main.cmd_list')
    def test_main_list_command(self, mock_cmd, mock_config):
        """Test main with list command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'list']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    def test_main_no_command(self, mock_config):
        """Test main with no command shows help."""
        with patch.object(sys, 'argv', ['prog']):
            with pytest.raises(SystemExit) as exc:
                main.main()

            assert exc.value.code == 1

    @patch('src.main.get_config')
    def test_main_config_not_found(self, mock_config):
        """Test main with missing config."""
        mock_config.side_effect = FileNotFoundError("Not found")

        with patch.object(sys, 'argv', ['prog', 'list']):
            with pytest.raises(SystemExit) as exc:
                main.main()

            assert exc.value.code == 1

    @patch('src.main.get_config')
    @patch('src.main.cmd_stats')
    def test_main_stats_command(self, mock_cmd, mock_config):
        """Test main with stats command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'stats']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_categories')
    def test_main_categories_command(self, mock_cmd, mock_config):
        """Test main with categories command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'categories']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_search')
    def test_main_search_command(self, mock_cmd, mock_config):
        """Test main with search command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'search', 'test']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_parsers')
    def test_main_parsers_command(self, mock_cmd, mock_config):
        """Test main with parsers command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'parsers']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_import')
    def test_main_import_command(self, mock_cmd, mock_config):
        """Test main with import command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'import']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_watch')
    def test_main_watch_command(self, mock_cmd, mock_config):
        """Test main with watch command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'watch']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_chat')
    def test_main_chat_command(self, mock_cmd, mock_config):
        """Test main with chat command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'chat']):
            main.main()

        mock_cmd.assert_called_once()

    def test_main_custom_config(self, tmp_path):
        """Test main with custom config path."""
        import yaml

        config_file = tmp_path / "custom.yaml"
        config_data = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": str(tmp_path / "test.db"), "statements_dir": str(tmp_path)},
        }
        config_file.write_text(yaml.dump(config_data))

        with patch.object(sys, 'argv', ['prog', '-c', str(config_file), 'stats']):
            with patch('src.main.cmd_stats') as mock_cmd:
                main.main()

                mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_list')
    def test_main_list_with_limit(self, mock_cmd, mock_config):
        """Test main with list command and limit."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'list', '-n', '50']):
            main.main()

        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.limit == 50

    @patch('src.main.get_config')
    def test_main_unknown_command_fallback(self, mock_config):
        """Test main handles unknown command gracefully."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        # Manually patch argparse to return an unknown command
        with patch.object(sys, 'argv', ['prog', 'list']):
            with patch('argparse.ArgumentParser.parse_args') as mock_parse:
                mock_parse.return_value = argparse.Namespace(
                    command='unknown_command',
                    config='config.yaml'
                )
                # Should not raise, just print help
                main.main()

    @patch('src.main.get_config')
    @patch('src.main.cmd_rename')
    def test_main_rename_command(self, mock_cmd, mock_config):
        """Test main with rename command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'rename']):
            main.main()

        mock_cmd.assert_called_once()


class TestCmdRename:
    """Tests for cmd_rename function."""

    def test_rename_missing_directory(self, mock_args, tmp_path):
        """Test rename with missing statements directory."""
        config = {
            "paths": {"statements_dir": str(tmp_path / "nonexistent")}
        }

        with pytest.raises(SystemExit) as exc:
            cmd_rename(mock_args, config)

        assert exc.value.code == 1

    def test_rename_already_correct_format(self, mock_args, tmp_path):
        """Test rename skips files already in correct format."""
        # Create a file with correct format
        (tmp_path / "287_Oct_2025.pdf").write_bytes(b"dummy")

        config = {"paths": {"statements_dir": str(tmp_path)}}

        cmd_rename(mock_args, config)

        # File should still exist with same name
        assert (tmp_path / "287_Oct_2025.pdf").exists()

    @patch('src.main.pdfplumber.open')
    def test_rename_no_statement_number(self, mock_pdf, mock_args, tmp_path):
        """Test rename skips files without statement number."""
        # Create a PDF file
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"dummy")

        # Mock PDF with no statement number
        mock_page = Mock()
        mock_page.extract_text.return_value = "Some text without statement number"
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

        config = {"paths": {"statements_dir": str(tmp_path)}}

        cmd_rename(mock_args, config)

        # File should still exist with original name
        assert pdf_file.exists()

    @patch('src.main.pdfplumber.open')
    def test_rename_no_statement_date(self, mock_pdf, mock_args, tmp_path):
        """Test rename skips files without statement date."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"dummy")

        mock_page = Mock()
        mock_page.extract_text.return_value = "Tax Invoice/Statement Number : 287"
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

        config = {"paths": {"statements_dir": str(tmp_path)}}

        cmd_rename(mock_args, config)

        assert pdf_file.exists()

    @patch('src.main.pdfplumber.open')
    def test_rename_success(self, mock_pdf, mock_args, tmp_path):
        """Test successful rename."""
        pdf_file = tmp_path / "old_name.pdf"
        pdf_file.write_bytes(b"dummy")

        mock_page = Mock()
        mock_page.extract_text.return_value = """
            Tax Invoice/Statement Number : 287
            Statement Date : 1 October 2025
        """
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

        config = {"paths": {"statements_dir": str(tmp_path)}}

        cmd_rename(mock_args, config)

        # Original file should not exist
        assert not pdf_file.exists()
        # New file should exist
        assert (tmp_path / "287_Oct_2025.pdf").exists()

    @patch('src.main.pdfplumber.open')
    def test_rename_abbreviated_month(self, mock_pdf, mock_args, tmp_path):
        """Test rename with abbreviated month format."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"dummy")

        mock_page = Mock()
        mock_page.extract_text.return_value = """
            Tax Invoice/Statement Number : 288
            Statement Date : 15 Nov 2025
        """
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

        config = {"paths": {"statements_dir": str(tmp_path)}}

        cmd_rename(mock_args, config)

        assert (tmp_path / "288_Nov_2025.pdf").exists()

    @patch('src.main.pdfplumber.open')
    def test_rename_target_exists(self, mock_pdf, mock_args, tmp_path):
        """Test rename skips if target file exists."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"dummy")
        # Create existing target
        (tmp_path / "287_Oct_2025.pdf").write_bytes(b"existing")

        mock_page = Mock()
        mock_page.extract_text.return_value = """
            Tax Invoice/Statement Number : 287
            Statement Date : 1 October 2025
        """
        mock_pdf.return_value.__enter__.return_value.pages = [mock_page]

        config = {"paths": {"statements_dir": str(tmp_path)}}

        cmd_rename(mock_args, config)

        # Original file should still exist
        assert pdf_file.exists()

    @patch('src.main.pdfplumber.open')
    def test_rename_handles_error(self, mock_pdf, mock_args, tmp_path):
        """Test rename handles PDF parsing errors."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"dummy")

        mock_pdf.side_effect = Exception("PDF error")

        config = {"paths": {"statements_dir": str(tmp_path)}}

        # Should not raise
        cmd_rename(mock_args, config)

        # File should still exist
        assert pdf_file.exists()


class TestCmdReimport:
    """Tests for cmd_reimport function."""

    @patch('src.main.reimport_statement')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_success(self, mock_db, mock_classifier, mock_reimport, mock_config, tmp_path):
        """Test successful reimport."""
        mock_classifier.return_value.check_connection.return_value = True
        mock_reimport.return_value = True

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        args = argparse.Namespace(file=str(pdf_file), bank=None, all=False)
        cmd_reimport(args, mock_config)

        mock_reimport.assert_called_once()

    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_file_not_found(self, mock_db, mock_classifier, mock_config, tmp_path):
        """Test reimport with non-existent file."""
        mock_classifier.return_value.check_connection.return_value = True
        args = argparse.Namespace(file=str(tmp_path / "nonexistent.pdf"), bank=None, all=False)

        with pytest.raises(SystemExit) as exc:
            cmd_reimport(args, mock_config)

        assert exc.value.code == 1

    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_no_ollama_connection(self, mock_db, mock_classifier, mock_config, tmp_path):
        """Test reimport fails when Ollama not connected."""
        mock_classifier.return_value.check_connection.return_value = False

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        args = argparse.Namespace(file=str(pdf_file), bank=None, all=False)

        with pytest.raises(SystemExit) as exc:
            cmd_reimport(args, mock_config)

        assert exc.value.code == 1

    @patch('src.main.reimport_statement')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_with_bank_override(self, mock_db, mock_classifier, mock_reimport, mock_config, tmp_path):
        """Test reimport with --bank override."""
        mock_classifier.return_value.check_connection.return_value = True
        mock_reimport.return_value = True

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        args = argparse.Namespace(file=str(pdf_file), bank="standardbank", all=False)
        cmd_reimport(args, mock_config)

        call_kwargs = mock_reimport.call_args.kwargs
        assert call_kwargs["bank"] == "standardbank"

    @patch('src.main.reimport_statement')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_failure(self, mock_db, mock_classifier, mock_reimport, mock_config, tmp_path):
        """Test reimport exits with error when reimport fails."""
        mock_classifier.return_value.check_connection.return_value = True
        mock_reimport.return_value = False

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        args = argparse.Namespace(file=str(pdf_file), bank=None, all=False)

        with pytest.raises(SystemExit) as exc:
            cmd_reimport(args, mock_config)

        assert exc.value.code == 1

    @patch('src.main.reimport_statement')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_all(self, mock_db, mock_classifier, mock_reimport, mock_config, tmp_path):
        """Test reimport --all imports all PDF files."""
        mock_classifier.return_value.check_connection.return_value = True
        mock_reimport.return_value = True

        # Create test PDF files
        (tmp_path / "test1.pdf").touch()
        (tmp_path / "test2.pdf").touch()
        (tmp_path / "test3.pdf").touch()

        # Update config to use tmp_path as statements dir
        config = mock_config.copy()
        config["paths"]["statements_dir"] = str(tmp_path)

        args = argparse.Namespace(file=None, bank=None, all=True)
        cmd_reimport(args, config)

        # Should have called reimport_statement 3 times
        assert mock_reimport.call_count == 3

    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_all_empty_directory(self, mock_db, mock_classifier, mock_config, tmp_path):
        """Test reimport --all with no PDF files in directory."""
        mock_classifier.return_value.check_connection.return_value = True

        # Empty directory - no PDF files
        config = mock_config.copy()
        config["paths"]["statements_dir"] = str(tmp_path)

        args = argparse.Namespace(file=None, bank=None, all=True)
        cmd_reimport(args, config)  # Should return without error

    @patch('src.main.reimport_statement')
    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_all_with_failures(self, mock_db, mock_classifier, mock_reimport, mock_config, tmp_path):
        """Test reimport --all handles failed reimports."""
        mock_classifier.return_value.check_connection.return_value = True
        # First succeeds, second fails
        mock_reimport.side_effect = [True, False]

        # Create test PDF files
        (tmp_path / "test1.pdf").touch()
        (tmp_path / "test2.pdf").touch()

        config = mock_config.copy()
        config["paths"]["statements_dir"] = str(tmp_path)

        args = argparse.Namespace(file=None, bank=None, all=True)
        cmd_reimport(args, config)

        assert mock_reimport.call_count == 2

    @patch('src.main.TransactionClassifier')
    @patch('src.main.Database')
    def test_reimport_no_file_no_all(self, mock_db, mock_classifier, mock_config):
        """Test reimport exits with error when no file and no --all."""
        args = argparse.Namespace(file=None, bank=None, all=False)

        with pytest.raises(SystemExit) as exc:
            cmd_reimport(args, mock_config)

        assert exc.value.code == 1

    @patch('src.main.get_config')
    @patch('src.main.cmd_reimport')
    def test_main_reimport_command(self, mock_cmd, mock_config, tmp_path):
        """Test main with reimport command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch.object(sys, 'argv', ['prog', 'reimport', str(pdf_file)]):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_reimport')
    def test_main_reimport_with_bank_option(self, mock_cmd, mock_config, tmp_path):
        """Test main with reimport command and --bank option."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        pdf_file = tmp_path / "test.pdf"
        pdf_file.touch()

        with patch.object(sys, 'argv', ['prog', 'reimport', str(pdf_file), '--bank', 'standardbank']):
            main.main()

        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.bank == "standardbank"


class TestCmdServe:
    """Tests for cmd_serve function."""

    def test_serve_starts_server(self, mock_config):
        """Test serve starts uvicorn server."""
        args = argparse.Namespace(host="127.0.0.1", port=8000)

        with patch('uvicorn.run') as mock_run:
            with patch('src.main.console'):
                cmd_serve(args, mock_config)

            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert call_args.kwargs["host"] == "127.0.0.1"
            assert call_args.kwargs["port"] == 8000

    def test_serve_custom_host_port(self, mock_config):
        """Test serve with custom host and port."""
        args = argparse.Namespace(host="0.0.0.0", port=3000)

        with patch('uvicorn.run') as mock_run:
            with patch('src.main.console'):
                cmd_serve(args, mock_config)

            call_args = mock_run.call_args
            assert call_args.kwargs["host"] == "0.0.0.0"
            assert call_args.kwargs["port"] == 3000

    @patch('src.main.get_config')
    @patch('src.main.cmd_serve')
    def test_main_serve_command(self, mock_cmd, mock_config):
        """Test main with serve command."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'serve']):
            main.main()

        mock_cmd.assert_called_once()

    @patch('src.main.get_config')
    @patch('src.main.cmd_serve')
    def test_main_serve_with_options(self, mock_cmd, mock_config):
        """Test main with serve command and options."""
        mock_config.return_value = {
            "bank": "fnb",
            "ollama": {"host": "localhost", "port": 11434, "model": "llama3.2"},
            "paths": {"database": "test.db", "statements_dir": "./statements"},
        }

        with patch.object(sys, 'argv', ['prog', 'serve', '--host', '0.0.0.0', '--port', '3000']):
            main.main()

        mock_cmd.assert_called_once()
        args = mock_cmd.call_args[0][0]
        assert args.host == "0.0.0.0"
        assert args.port == 3000
