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


class TestClearContext:
    """Tests for clearing chat context."""

    def test_clear_context_clears_history(self, mock_db):
        """Test clear_context clears conversation history and transactions."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            # Populate history and transactions
            chat._conversation_history = [{"role": "user", "content": "test"}]
            chat._last_transactions = [{"description": "Test", "amount": 100}]

            chat.clear_context()

            assert chat._conversation_history == []
            assert chat._last_transactions == []


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

    def test_greeting_returns_empty(self, chat, mock_db):
        """Test greetings return no transactions."""
        result = chat._find_relevant_transactions("hello")
        assert result == []
        mock_db.get_all_transactions.assert_not_called()

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
        """Test falling back to recent transactions for vague queries."""
        mock_db.search_transactions.return_value = []

        chat._find_relevant_transactions("show recent transactions")

        mock_db.get_all_transactions.assert_called_with(limit=20)

    def test_specific_query_no_fallback(self, chat, mock_db):
        """Test specific queries don't fallback to recent transactions."""
        mock_db.search_transactions.return_value = []

        result = chat._find_relevant_transactions("flowers for fiancé")

        mock_db.get_all_transactions.assert_not_called()
        assert result == []

    def test_hyphen_variation_removes_hyphen(self, chat, mock_db):
        """Test search tries removing hyphen from terms like x-ray."""
        xray_results = [{"description": "X-Rays", "amount": 500}]
        # First call (x-ray) returns nothing, second call (xray) returns results
        mock_db.search_transactions.side_effect = [[], xray_results]

        result = chat._find_relevant_transactions("show x-ray")

        assert result == xray_results
        # Should have tried both "x-ray" and "xray"
        assert mock_db.search_transactions.call_count == 2

    def test_hyphen_variation_adds_hyphen(self, chat, mock_db):
        """Test search tries adding hyphen for terms like xray -> x-ray."""
        xray_results = [{"description": "X-Rays", "amount": 500}]
        # First call (xray) returns nothing, second call (x-ray) returns results
        mock_db.search_transactions.side_effect = [[], xray_results]

        result = chat._find_relevant_transactions("show xray")

        assert result == xray_results
        # Should have tried both "xray" and "x-ray"
        assert mock_db.search_transactions.call_count == 2

    def test_find_category_with_date_range(self, chat, mock_db):
        """Test finding category transactions within a date range."""
        mock_db.get_transactions_in_date_range.return_value = [
            {"date": "2025-12-15", "description": "Woolworths", "amount": 500, "category": "groceries"},
            {"date": "2025-12-20", "description": "Shell Fuel", "amount": 800, "category": "fuel"},
            {"date": "2025-12-25", "description": "Checkers", "amount": 300, "category": "groceries"},
        ]

        result = chat._find_relevant_transactions("groceries last month")

        # Should call date range query
        mock_db.get_transactions_in_date_range.assert_called()
        # Should filter by category and return only groceries
        assert len(result) == 2
        assert all(tx["category"] == "groceries" for tx in result)

    def test_when_last_returns_only_most_recent(self, chat, mock_db):
        """Test 'when last' queries return only the most recent transaction."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-10", "description": "Woolworths", "amount": 500, "category": "groceries"},
            {"date": "2025-01-20", "description": "Checkers", "amount": 300, "category": "groceries"},
            {"date": "2025-01-15", "description": "Spar", "amount": 200, "category": "groceries"},
        ]

        result = chat._find_relevant_transactions("when last did I buy groceries")

        # Should return only the most recent (2025-01-20)
        assert len(result) == 1
        assert result[0]["date"] == "2025-01-20"
        assert result[0]["description"] == "Checkers"


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

    def test_build_context_with_credit_transaction(self, chat, mock_db):
        """Test building context with credit transactions calculates totals correctly."""
        transactions = [
            {
                "date": "2025-01-15",
                "description": "Salary Payment",
                "amount": 10000.00,
                "category": "salary",
                "transaction_type": "credit",
            },
            {
                "date": "2025-01-16",
                "description": "Groceries",
                "amount": 500.00,
                "category": "groceries",
                "transaction_type": "debit",
            }
        ]

        context = chat._build_context(transactions, "test query")

        assert "10,000.00" in context
        assert "500.00" in context
        # Check pre-calculated totals include counts and amounts
        assert "1 PAYMENTS TOTALING: R500.00" in context
        assert "1 DEPOSITS TOTALING: R10,000.00" in context

    def test_build_context_when_last_skips_totals(self, chat, mock_db):
        """Test 'when last' queries don't show totals."""
        transactions = [
            {
                "date": "2025-01-15",
                "description": "Dr Oosthuizen",
                "amount": 1140.00,
                "category": "medical",
                "transaction_type": "debit",
            }
        ]

        context = chat._build_context(transactions, "when last did I pay the doctor")

        assert "1,140.00" in context
        assert "TOTAL SPENT" not in context
        assert "TOTAL RECEIVED" not in context

    def test_build_context_price_increase_query(self, chat, mock_db):
        """Test price change query includes detected price change."""
        transactions = [
            {"date": "2025-03-01", "description": "Spotify", "amount": 99.99, "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-04-01", "description": "Spotify", "amount": 99.99, "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-05-01", "description": "Spotify", "amount": 119.99, "category": "subscriptions", "transaction_type": "debit"},
        ]

        context = chat._build_context(transactions, "when did the spotify price increase")

        assert "PRICE INCREASED in May 2025 from R99.99 to R119.99" in context

    def test_build_context_price_change_no_change(self, chat, mock_db):
        """Test price change query when no change detected."""
        transactions = [
            {"date": "2025-03-01", "description": "Spotify", "amount": 99.99, "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-04-01", "description": "Spotify", "amount": 99.99, "category": "subscriptions", "transaction_type": "debit"},
        ]

        context = chat._build_context(transactions, "when did the spotify price change")

        assert "NO PRICE CHANGE DETECTED" in context


class TestPriceChangeDetection:
    """Tests for price change detection."""

    def test_detect_price_increase(self, chat):
        """Test detecting a price increase."""
        transactions = [
            {"date": "2025-08-01", "amount": 99.99},
            {"date": "2025-09-01", "amount": 119.99},
            {"date": "2025-10-01", "amount": 119.99},
        ]

        result = chat._detect_price_change(transactions)

        assert result == "PRICE INCREASED in September 2025 from R99.99 to R119.99"

    def test_detect_price_decrease(self, chat):
        """Test detecting a price decrease."""
        transactions = [
            {"date": "2025-08-01", "amount": 119.99},
            {"date": "2025-09-01", "amount": 99.99},
        ]

        result = chat._detect_price_change(transactions)

        assert result == "PRICE DECREASED in September 2025 from R119.99 to R99.99"

    def test_detect_no_price_change(self, chat):
        """Test no change when amounts are same."""
        transactions = [
            {"date": "2025-08-01", "amount": 99.99},
            {"date": "2025-09-01", "amount": 99.99},
            {"date": "2025-10-01", "amount": 99.99},
        ]

        result = chat._detect_price_change(transactions)

        assert result is None

    def test_detect_price_change_empty_list(self, chat):
        """Test with empty transaction list."""
        result = chat._detect_price_change([])
        assert result is None

    def test_detect_price_change_single_transaction(self, chat):
        """Test with single transaction."""
        transactions = [{"date": "2025-08-01", "amount": 99.99}]
        result = chat._detect_price_change(transactions)
        assert result is None

    def test_detect_price_change_same_month_transactions(self, chat):
        """Test with multiple transactions all in same month."""
        transactions = [
            {"date": "2025-08-01", "amount": 99.99},
            {"date": "2025-08-15", "amount": 99.99},
            {"date": "2025-08-25", "amount": 99.99},
        ]
        result = chat._detect_price_change(transactions)
        assert result is None

    def test_detect_price_change_unsorted_input(self, chat):
        """Test that unsorted transactions are handled correctly."""
        # Input is not sorted - function should sort it
        transactions = [
            {"date": "2025-10-01", "amount": 119.99},
            {"date": "2025-08-01", "amount": 99.99},
            {"date": "2025-09-01", "amount": 119.99},
        ]

        result = chat._detect_price_change(transactions)

        # Should detect change in Sept (first occurrence of new price when sorted)
        assert result == "PRICE INCREASED in September 2025 from R99.99 to R119.99"

    def test_detect_price_change_excludes_fees(self, chat):
        """Test that fee transactions are excluded from price detection."""
        # Mix of subscription and fee transactions (like Spotify + int'l payment fees)
        transactions = [
            {"date": "2025-08-28", "amount": 99.99, "category": "subscriptions"},
            {"date": "2025-08-29", "amount": 2.50, "category": "fees"},
            {"date": "2025-09-28", "amount": 119.99, "category": "subscriptions"},
            {"date": "2025-09-29", "amount": 3.00, "category": "fees"},
            {"date": "2025-10-28", "amount": 119.99, "category": "subscriptions"},
            {"date": "2025-10-29", "amount": 3.00, "category": "fees"},
        ]

        result = chat._detect_price_change(transactions)

        # Should detect subscription price change, ignoring fees
        assert result == "PRICE INCREASED in September 2025 from R99.99 to R119.99"

    def test_detect_price_change_only_fees_returns_none(self, chat):
        """Test that if only fee transactions remain after filtering, returns None."""
        transactions = [
            {"date": "2025-08-29", "amount": 2.50, "category": "fees"},
            {"date": "2025-09-29", "amount": 3.00, "category": "fees"},
        ]

        result = chat._detect_price_change(transactions)
        assert result is None


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

    def test_ask_follow_up_uses_previous_transactions(self, mock_db):
        """Test ask method uses previous transactions for follow-up queries."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Woolworths", "amount": 500,
             "category": "groceries", "transaction_type": "debit"}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {
                "message": {"content": "Response"}
            }

            # First query - should fetch transactions
            chat.ask("show groceries")
            assert len(chat._last_transactions) == 1

            # Reset mock to verify it's not called again
            mock_db.get_transactions_by_category.reset_mock()

            # Follow-up query - should use previous transactions
            chat.ask("list them")

            # Should NOT have fetched new transactions
            mock_db.get_transactions_by_category.assert_not_called()
            mock_db.search_transactions.assert_not_called()


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

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            # These keywords should NOT trigger get_transactions_by_type
            # but should fall through to search, then return empty (no fallback)
            result = chat._find_relevant_transactions("show my expenses")

            # Should NOT have called get_transactions_by_type for debits
            # (because returning all debits is too many)
            # Also should not fallback since this is a specific query
            mock_db.get_all_transactions.assert_not_called()
            assert result == []

    def test_find_payment_keyword_falls_through(self, mock_db):
        """Test payment keyword falls through to search, no fallback."""
        mock_db.search_transactions.return_value = []

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            result = chat._find_relevant_transactions("show payment history")

            # Specific query - no fallback to recent transactions
            mock_db.get_all_transactions.assert_not_called()
            assert result == []

    def test_fee_search_keeps_fees(self, mock_db):
        """Test searching for fees keeps fee transactions."""
        fee_transactions = [
            {"description": "Service Fee", "amount": 5, "category": "fees"},
            {"description": "Monthly Fee", "amount": 10, "category": "fees"},
        ]
        mock_db.search_transactions.return_value = fee_transactions

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            result = chat._find_relevant_transactions("show my fees")

            # Should keep fee transactions when searching for fees
            assert len(result) == 2


class TestFollowUpDetection:
    """Tests for follow-up query detection."""

    def test_greeting_not_follow_up(self, mock_db):
        """Test greetings are never detected as follow-ups."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            assert chat._is_follow_up_query("hi") is False
            assert chat._is_follow_up_query("hello") is False
            assert chat._is_follow_up_query("thanks") is False

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

    def test_category_name_query_not_follow_up(self, mock_db):
        """Test short query with category name is not follow-up."""
        # "airtime" is a category but not in the hardcoded keywords
        mock_db.get_all_categories.return_value = ["airtime", "groceries", "fuel"]
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            # Short query (≤5 words) with category name should NOT be follow-up
            assert chat._is_follow_up_query("how much airtime?") is False

    def test_pay_name_query_not_follow_up(self, mock_db):
        """Test 'Did I pay Name?' is not a follow-up."""
        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            # "Did I pay Paul?" should trigger a new search, not be a follow-up
            assert chat._is_follow_up_query("Did I pay Paul?") is False
            assert chat._is_follow_up_query("Have I paid John?") is False


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
        """Test follow-up with no previous transactions tries to fetch new."""
        mock_db.search_transactions.return_value = []

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._client.chat.return_value = {"message": {"content": "Response"}}
            chat._last_transactions = []  # Empty

            # Even though it looks like follow-up, should try to fetch new
            # Use vague query that triggers fallback
            chat._process_query("show recent transactions")

            mock_db.get_all_transactions.assert_called()


class TestBudgetQueries:
    """Tests for budget-related query handling."""

    def test_budget_query_filters_to_latest_statement(self, mock_db):
        """Test budget queries with category filter to latest statement."""
        mock_db.get_all_categories.return_value = ["groceries", "fuel", "electricity"]
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": "287", "statement_date": "2025-12-01"
        }
        mock_db.get_transactions_by_statement.return_value = [
            {"date": "2025-12-15", "description": "Electricity", "amount": 2000,
             "category": "electricity", "transaction_type": "debit"},
            {"date": "2025-12-16", "description": "Groceries", "amount": 500,
             "category": "groceries", "transaction_type": "debit"}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            result = chat._find_relevant_transactions("How much of my electricity budget have I used?")

            mock_db.get_latest_statement.assert_called()
            mock_db.get_transactions_by_statement.assert_called_with("287")
            # Should only return electricity transactions
            assert len(result) == 1
            assert result[0]["category"] == "electricity"

    def test_general_budget_query_returns_no_transactions(self, mock_db):
        """Test general budget queries return no transactions."""
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": "287", "statement_date": "2025-12-01"
        }

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            result = chat._find_relevant_transactions("How much budget remaining?")

            # Should return empty list for general budget queries
            assert result == []

    def test_budget_query_with_category_filters_both(self, mock_db):
        """Test budget query with category filters to latest statement AND category."""
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": "287", "statement_date": "2025-12-01"
        }
        mock_db.get_transactions_by_statement.return_value = [
            {"date": "2025-12-15", "description": "Electricity", "amount": 2000,
             "category": "utilities", "transaction_type": "debit"},
            {"date": "2025-12-16", "description": "Groceries", "amount": 500,
             "category": "groceries", "transaction_type": "debit"},
        ]
        mock_db.get_all_categories.return_value = ["utilities", "groceries"]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            result = chat._find_relevant_transactions("How much of my utilities budget?")

            # Should only return utilities transactions
            assert len(result) == 1
            assert result[0]["category"] == "utilities"

    def test_budget_context_includes_budget_info(self, mock_db):
        """Test build_context includes budget info for budget queries."""
        mock_db.get_stats.return_value = {"total_transactions": 100}
        mock_db.get_all_budgets.return_value = [
            {"category": "utilities", "amount": 3000},
            {"category": "groceries", "amount": 10000},
        ]
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": "287", "statement_date": "2025-12-01"
        }
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "utilities", "total_debits": 2000, "count": 1},
            {"category": "groceries", "total_debits": 8000, "count": 5},
        ]

        transactions = [
            {"date": "2025-12-15", "description": "Test", "amount": 2000,
             "category": "utilities", "transaction_type": "debit"}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            context = chat._build_context(transactions, "How much of my budget have I used?")

            assert "Budget status" in context
            assert "utilities" in context
            assert "R2,000.00 spent of R3,000.00 budget" in context
            assert "Latest statement: #287" in context

    def test_budget_context_shows_over_budget(self, mock_db):
        """Test budget context shows OVER BUDGET status."""
        mock_db.get_stats.return_value = {"total_transactions": 100}
        mock_db.get_all_budgets.return_value = [
            {"category": "utilities", "amount": 1500},
        ]
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": "287", "statement_date": "2025-12-01"
        }
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "utilities", "total_debits": 2000, "count": 1},
        ]

        transactions = [{"date": "2025-12-15", "description": "Test", "amount": 2000,
                        "category": "utilities", "transaction_type": "debit"}]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            context = chat._build_context(transactions, "budget status")

            assert "OVER BUDGET" in context

    def test_non_budget_query_no_budget_info(self, mock_db):
        """Test non-budget queries don't include budget info."""
        mock_db.get_stats.return_value = {"total_transactions": 100}

        transactions = [{"date": "2025-12-15", "description": "Test", "amount": 500,
                        "category": "groceries", "transaction_type": "debit"}]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            context = chat._build_context(transactions, "show groceries")

            # Should NOT have budget info
            assert "Budget status" not in context
            mock_db.get_all_budgets.assert_not_called()


class TestSynonymExpansion:
    """Tests for category synonym expansion."""

    def test_saved_expands_to_savings(self, mock_db):
        """Test 'saved' query finds savings category."""
        mock_db.get_all_categories.return_value = ["groceries", "savings", "fuel"]
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Transfer to savings", "amount": 1000}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._find_relevant_transactions("how much have I saved")

            mock_db.get_transactions_by_category.assert_called_with("savings")

    def test_doctor_expands_to_medical(self, mock_db):
        """Test 'doctor' query finds medical category."""
        mock_db.get_all_categories.return_value = ["groceries", "medical", "fuel"]
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Dr Smith", "amount": 500}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._find_relevant_transactions("when did I pay the doctor")

            mock_db.get_transactions_by_category.assert_called_with("medical")

    def test_petrol_expands_to_fuel(self, mock_db):
        """Test 'petrol' query finds fuel category."""
        mock_db.get_all_categories.return_value = ["groceries", "fuel", "medical"]
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Shell", "amount": 800}
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            chat._find_relevant_transactions("how much petrol did I buy")

            mock_db.get_transactions_by_category.assert_called_with("fuel")


class TestDateRangeOnly:
    """Tests for date range only queries (no category match)."""

    def test_date_range_only_returns_transactions(self, mock_db):
        """Test date range query without category returns date range transactions."""
        mock_db.get_all_categories.return_value = ["groceries", "fuel"]
        mock_db.get_transactions_in_date_range.return_value = [
            {"date": "2025-12-15", "description": "Transaction 1", "amount": 100},
            {"date": "2025-12-20", "description": "Transaction 2", "amount": 200},
        ]

        with patch('src.chat.ollama.Client'):
            chat = ChatInterface(mock_db)
            result = chat._find_relevant_transactions("show me last month")

            mock_db.get_transactions_in_date_range.assert_called()
            assert len(result) == 2
