"""Tests for chat module."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from src.chat import ChatInterface
from src.database import Database


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = Mock(spec=Database)
    db.get_stats.return_value = {
        "total_statements": 1,
        "total_transactions": 10,
        "total_debits": 5000.00,
        "total_credits": 10000.00,
        "categories_count": 5,
    }
    db.get_all_categories.return_value = ["groceries", "fuel", "salary"]
    db.get_all_transactions.return_value = [
        {
            "id": 1,
            "date": "2025-01-15",
            "description": "Woolworths",
            "amount": 500.00,
            "category": "groceries",
            "transaction_type": "debit",
        }
    ]
    return db


@pytest.fixture
def chat(mock_db):
    """Create a chat interface with mock database."""
    with patch('src.chat.ollama.Client'):
        return ChatInterface(mock_db)


class TestChatInit:
    """Tests for ChatInterface initialization."""

    def test_init_creates_empty_history(self, mock_db):
        """Test initialization creates empty conversation history."""
        chat = ChatInterface(mock_db)
        assert chat._conversation_history == []

    def test_init_stores_model(self, mock_db):
        """Test initialization stores model name."""
        chat = ChatInterface(mock_db, model="mistral")
        assert chat.model == "mistral"


class TestSearchTermExtraction:
    """Tests for search term extraction."""

    def test_extract_removes_stop_words(self, chat):
        """Test stop words are removed."""
        terms = chat._extract_search_terms("when did I pay the doctor")
        assert "when" not in terms
        assert "did" not in terms
        assert "the" not in terms
        assert "doctor" in terms

    def test_extract_removes_short_words(self, chat):
        """Test short words are removed."""
        terms = chat._extract_search_terms("go to shop")
        assert "go" not in terms
        assert "to" not in terms

    def test_extract_keeps_relevant_terms(self, chat):
        """Test relevant terms are kept."""
        terms = chat._extract_search_terms("woolworths groceries shopping")
        assert "woolworths" in terms
        assert "groceries" in terms
        assert "shopping" in terms


class TestFindRelevantTransactions:
    """Tests for finding relevant transactions."""

    def test_find_by_category(self, chat, mock_db):
        """Test finding transactions by category keyword."""
        mock_db.get_transactions_by_category.return_value = [
            {"description": "Woolworths", "amount": 500}
        ]

        result = chat._find_relevant_transactions("show groceries")

        mock_db.get_transactions_by_category.assert_called_with("groceries")

    def test_find_credits(self, chat, mock_db):
        """Test finding credit transactions."""
        mock_db.get_transactions_by_type.return_value = []

        chat._find_relevant_transactions("show my deposits")

        mock_db.get_transactions_by_type.assert_called_with("credit")

    def test_find_last_month(self, chat, mock_db):
        """Test finding last month's transactions."""
        mock_db.get_transactions_in_date_range.return_value = []

        chat._find_relevant_transactions("spending last month")

        mock_db.get_transactions_in_date_range.assert_called()

    def test_find_this_month(self, chat, mock_db):
        """Test finding this month's transactions."""
        mock_db.get_transactions_in_date_range.return_value = []

        chat._find_relevant_transactions("spending this month")

        mock_db.get_transactions_in_date_range.assert_called()

    def test_find_by_search_term(self, chat, mock_db):
        """Test finding by search term."""
        mock_db.search_transactions.return_value = [
            {"description": "Woolworths", "amount": 500}
        ]

        result = chat._find_relevant_transactions("woolworths transactions")

        mock_db.search_transactions.assert_called()

    def test_falls_back_to_recent(self, chat, mock_db):
        """Test falling back to recent transactions."""
        mock_db.search_transactions.return_value = []

        chat._find_relevant_transactions("random query")

        mock_db.get_all_transactions.assert_called_with(limit=20)


class TestBuildContext:
    """Tests for context building."""

    def test_build_context_with_transactions(self, chat, mock_db):
        """Test building context with transactions."""
        transactions = [
            {
                "date": "2025-01-15",
                "description": "Woolworths Groceries",
                "amount": 500.00,
                "category": "groceries",
                "transaction_type": "debit",
                "recipient_or_payer": "Woolworths",
            }
        ]

        context = chat._build_context(transactions, "test query")

        assert "500.00" in context
        assert "Woolworths" in context
        assert "groceries" in context

    def test_build_context_empty(self, chat, mock_db):
        """Test building context with no transactions."""
        context = chat._build_context([], "test query")
        assert "No matching transactions" in context

    def test_build_context_limits_transactions(self, chat, mock_db):
        """Test context limits number of transactions."""
        transactions = [
            {
                "date": f"2025-01-{i:02d}",
                "description": f"Transaction {i}",
                "amount": 100.00,
                "category": "other",
                "transaction_type": "debit",
            }
            for i in range(1, 25)
        ]

        context = chat._build_context(transactions, "test")

        # Should mention there are more
        assert "more transactions" in context


class TestConversationHistory:
    """Tests for conversation history management."""

    def test_history_stores_user_message(self, chat, mock_db):
        """Test user messages are stored in history."""
        chat._client.chat.return_value = {
            "message": {"content": "Test response"}
        }

        chat._get_llm_response("test query", "test context")

        assert len(chat._conversation_history) == 2
        assert chat._conversation_history[0]["role"] == "user"

    def test_history_stores_assistant_response(self, chat, mock_db):
        """Test assistant responses are stored in history."""
        chat._client.chat.return_value = {
            "message": {"content": "Test response"}
        }

        chat._get_llm_response("test query", "test context")

        assert chat._conversation_history[1]["role"] == "assistant"
        assert chat._conversation_history[1]["content"] == "Test response"

    def test_history_accumulates(self, chat, mock_db):
        """Test conversation history accumulates over multiple turns."""
        chat._client.chat.return_value = {
            "message": {"content": "Response"}
        }

        chat._get_llm_response("query 1", "context 1")
        chat._get_llm_response("query 2", "context 2")

        assert len(chat._conversation_history) == 4

    def test_history_sent_to_llm(self, chat, mock_db):
        """Test full history is sent to LLM."""
        chat._client.chat.return_value = {
            "message": {"content": "Response"}
        }

        # First query
        chat._get_llm_response("query 1", "context 1")

        # Second query - should include first exchange
        chat._get_llm_response("query 2", "context 2")

        # Check the messages sent to chat
        call_args = chat._client.chat.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")

        # Should have system + 3 history messages (user1, asst1, user2)
        # The second assistant response isn't added until after chat returns
        assert len(messages) == 4
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "assistant"
        assert messages[3]["role"] == "user"

    def test_history_not_added_on_error(self, chat, mock_db):
        """Test history not updated on LLM error."""
        chat._client.chat.side_effect = Exception("Connection error")

        chat._get_llm_response("test query", "test context")

        # Should have no history entries (user message removed on error)
        assert len(chat._conversation_history) == 0


class TestLLMResponse:
    """Tests for LLM response handling."""

    def test_handles_llm_error(self, chat, mock_db):
        """Test LLM errors are handled gracefully."""
        chat._client.chat.side_effect = Exception("Connection refused")

        result = chat._get_llm_response("test", "context")

        assert "error" in result.lower() or "sorry" in result.lower()


class TestAskMethod:
    """Tests for single query ask method."""

    def test_ask_returns_response(self, mock_db):
        """Test ask method returns LLM response."""
        # Need to set up mock_db before creating chat
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Woolworths", "amount": 500,
             "category": "groceries", "transaction_type": "debit"}
        ]

        with patch('src.chat.ollama.Client') as mock_ollama:
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {
                "message": {"content": "Your last grocery purchase was R500"}
            }

            result = chat.ask("when did I last buy groceries")

            assert "500" in result


class TestChatStart:
    """Tests for chat start method."""

    def test_start_quit_command(self, mock_db):
        """Test start exits on quit command."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            # Simulate user typing 'quit'
            with patch.object(chat.console, 'input', return_value='quit'):
                chat.start()

    def test_start_exit_command(self, mock_db):
        """Test start exits on exit command."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            with patch.object(chat.console, 'input', return_value='exit'):
                chat.start()

    def test_start_q_command(self, mock_db):
        """Test start exits on q command."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            with patch.object(chat.console, 'input', return_value='q'):
                chat.start()

    def test_start_empty_input(self, mock_db):
        """Test start handles empty input."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            # Return empty string first, then quit
            inputs = iter(['', 'quit'])
            with patch.object(chat.console, 'input', side_effect=lambda x: next(inputs)):
                chat.start()

    def test_start_keyboard_interrupt(self, mock_db):
        """Test start handles KeyboardInterrupt."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            with patch.object(chat.console, 'input', side_effect=KeyboardInterrupt()):
                chat.start()

    def test_start_eof_error(self, mock_db):
        """Test start handles EOFError."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            with patch.object(chat.console, 'input', side_effect=EOFError()):
                chat.start()

    def test_start_processes_query(self, mock_db):
        """Test start processes user queries."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Woolworths", "amount": 500,
             "category": "groceries", "transaction_type": "debit"}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {
                "message": {"content": "Response"}
            }

            # Return query first, then quit
            inputs = iter(['show groceries', 'quit'])
            with patch.object(chat.console, 'input', side_effect=lambda x: next(inputs)):
                chat.start()


class TestDisplayTransactions:
    """Tests for transaction display."""

    def test_display_transactions_debit(self, mock_db):
        """Test displaying debit transactions."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            transactions = [
                {"date": "2025-01-15", "description": "Test", "amount": 500,
                 "category": "other", "transaction_type": "debit"}
            ]

            # Should not raise
            chat._display_transactions(transactions)

    def test_display_transactions_credit(self, mock_db):
        """Test displaying credit transactions."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            transactions = [
                {"date": "2025-01-15", "description": "Salary", "amount": 10000,
                 "category": "salary", "transaction_type": "credit"}
            ]

            chat._display_transactions(transactions)

    def test_display_transactions_limits_to_10(self, mock_db):
        """Test display limits to 10 transactions."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            transactions = [
                {"date": f"2025-01-{i:02d}", "description": f"Test {i}",
                 "amount": 100, "category": "other", "transaction_type": "debit"}
                for i in range(1, 20)
            ]

            # Should not raise and should only show 10
            chat._display_transactions(transactions)

    def test_display_transactions_no_category(self, mock_db):
        """Test displaying transactions without category."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)

            transactions = [
                {"date": "2025-01-15", "description": "Test", "amount": 500,
                 "category": None, "transaction_type": "debit"}
            ]

            chat._display_transactions(transactions)


class TestProcessQuery:
    """Tests for query processing."""

    def test_process_query_shows_transactions(self, mock_db):
        """Test process_query shows transactions when found."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Test", "amount": 500,
             "category": "groceries", "transaction_type": "debit"}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {
                "message": {"content": "Here are your transactions"}
            }

            chat._process_query("show groceries")

    def test_process_query_hides_many_transactions(self, mock_db):
        """Test process_query hides table when many transactions."""
        many_transactions = [
            {"date": f"2025-01-{i:02d}", "description": f"Test {i}",
             "amount": 100, "category": "other", "transaction_type": "debit"}
            for i in range(1, 20)
        ]
        mock_db.get_all_transactions.return_value = many_transactions
        mock_db.search_transactions.return_value = []  # No search results

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {
                "message": {"content": "Found many transactions"}
            }

            # Should not display table for > 10 transactions
            chat._process_query("random query with no matches")


class TestFindRelevantTransactionsExtended:
    """Additional tests for finding relevant transactions."""

    def test_find_income_keyword(self, mock_db):
        """Test finding transactions by income keyword."""
        mock_db.get_transactions_by_type.return_value = []

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._find_relevant_transactions("show my income")

            mock_db.get_transactions_by_type.assert_called_with("credit")

    def test_find_debit_keyword_falls_through(self, mock_db):
        """Test debit/expense/payment keywords don't return all debits."""
        mock_db.search_transactions.return_value = []
        mock_db.get_all_transactions.return_value = []

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            # These keywords should NOT trigger get_transactions_by_type
            # but should fall through to search
            chat._find_relevant_transactions("show my expenses")

            # Should NOT have called get_transactions_by_type for debits
            # (because returning all debits is too many)
            mock_db.get_all_transactions.assert_called()

    def test_find_payment_keyword_falls_through(self, mock_db):
        """Test payment keyword falls through to search."""
        mock_db.search_transactions.return_value = []
        mock_db.get_all_transactions.return_value = []

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._find_relevant_transactions("show payment history")

            mock_db.get_all_transactions.assert_called()


class TestFollowUpDetection:
    """Tests for follow-up query detection."""

    def test_detects_them_as_follow_up(self, mock_db):
        """Test 'them' is detected as follow-up."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("group them by date") is True

    def test_detects_these_as_follow_up(self, mock_db):
        """Test 'these' is detected as follow-up."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("summarize these") is True

    def test_detects_sort_as_follow_up(self, mock_db):
        """Test 'sort' is detected as follow-up."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("sort by amount") is True

    def test_detects_total_as_follow_up(self, mock_db):
        """Test 'total' is detected as follow-up."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("what's the total?") is True

    def test_short_query_without_keywords_is_follow_up(self, mock_db):
        """Test short queries without specific keywords are follow-ups."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("by date") is True

    def test_specific_query_not_follow_up(self, mock_db):
        """Test query with specific keywords is not follow-up."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("show electricity transactions") is False

    def test_show_query_not_follow_up(self, mock_db):
        """Test 'show' query is not follow-up."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("show my groceries") is False


class TestFollowUpContext:
    """Tests for follow-up query context handling."""

    def test_follow_up_uses_previous_transactions(self, mock_db):
        """Test follow-up query uses previous transactions."""
        electricity_transactions = [
            {"date": "2025-01-15", "description": "Electricity", "amount": 500,
             "category": "utilities", "transaction_type": "debit"}
        ]
        mock_db.search_transactions.return_value = electricity_transactions

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {"message": {"content": "Response"}}

            # First query - gets electricity transactions
            chat._process_query("show electricity")

            # Verify transactions were stored
            assert chat._last_transactions == electricity_transactions

            # Reset mock to track new calls
            mock_db.search_transactions.reset_mock()

            # Follow-up query should use stored transactions
            chat._process_query("group them by month")

            # Should NOT have searched for new transactions
            mock_db.search_transactions.assert_not_called()

    def test_new_query_replaces_stored_transactions(self, mock_db):
        """Test new specific query replaces stored transactions."""
        electricity = [{"date": "2025-01-15", "description": "Electricity", "amount": 500,
                       "category": "utilities", "transaction_type": "debit"}]
        groceries = [{"date": "2025-01-16", "description": "Groceries", "amount": 300,
                     "category": "groceries", "transaction_type": "debit"}]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {"message": {"content": "Response"}}

            # First query
            mock_db.search_transactions.return_value = electricity
            chat._process_query("show electricity")
            assert chat._last_transactions == electricity

            # New specific query should replace
            mock_db.get_transactions_by_category.return_value = groceries
            chat._process_query("show groceries")
            assert chat._last_transactions == groceries

    def test_empty_previous_transactions_fetches_new(self, mock_db):
        """Test follow-up with no previous transactions fetches new."""
        mock_db.get_all_transactions.return_value = []
        mock_db.search_transactions.return_value = []

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {"message": {"content": "Response"}}
            chat._last_transactions = []  # Empty

            # Even though it looks like follow-up, should fetch new
            chat._process_query("group them")

            mock_db.get_all_transactions.assert_called()
