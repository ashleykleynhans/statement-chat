"""Integration tests for chat query handling.

These tests verify that various user queries are handled correctly,
including typo correction, budget management, and transaction searches.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.chat import ChatInterface


def mock_openai_response(content: str):
    """Create a mock OpenAI API response."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    return mock_response


@pytest.fixture
def mock_db():
    """Create a mock database with test data."""
    db = MagicMock()

    # Basic stats
    db.get_stats.return_value = {
        "total_transactions": 500,
        "total_statements": 12,
    }

    # Categories
    db.get_all_categories.return_value = [
        "medical", "groceries", "fuel", "subscriptions", "florist",
        "home_maintenance", "fees", "transfer", "salary", "other"
    ]

    # Default empty returns
    db.search_transactions.return_value = []
    db.get_transactions_by_category.return_value = []
    db.get_all_transactions.return_value = []
    db.get_transactions_in_date_range.return_value = []
    db.get_transactions_by_type.return_value = []
    db.get_all_budgets.return_value = []
    db.get_latest_statement.return_value = {"statement_number": 288, "statement_date": "2025-12-31"}
    db.get_category_summary_for_statement.return_value = []

    return db


@pytest.fixture
def chat(mock_db):
    """Create a ChatInterface with mocked dependencies."""
    with patch("src.chat.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        # with_options() returns a copy; keep the same mock so responses work
        mock_client.with_options.return_value = mock_client
        # Default LLM response
        mock_client.chat.completions.create.return_value = mock_openai_response("Test response")

        chat = ChatInterface(mock_db, host="localhost", port=1234, model="test-model")
        yield chat


class TestGreetings:
    """Test greeting handling."""

    def test_hi_returns_no_transactions(self, chat):
        """Greeting 'Hi' should return empty transactions."""
        response, transactions, _ = chat.ask("Hi")
        assert transactions == []

    def test_hello_returns_no_transactions(self, chat):
        """Greeting 'Hello' should return empty transactions."""
        response, transactions, _ = chat.ask("Hello")
        assert transactions == []


class TestDoctorQueries:
    """Test doctor/medical queries."""

    def test_when_last_paid_doctor(self, chat, mock_db):
        """'When last did I pay the doctor?' should return most recent doctor visit."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-01-15", "description": "Dr Smith Cardiologist", "amount": -850.00,
             "category": "medical", "transaction_type": "debit"},
            {"date": "2025-02-20", "description": "Medicross Consultation", "amount": -650.00,
             "category": "medical", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("When last did I pay the doctor?")

        # Should return only the most recent (when last = 1 transaction)
        assert len(transactions) == 1
        assert transactions[0]["date"] == "2025-02-20"


class TestBudgetQueries:
    """Test budget-related queries."""

    def test_overall_budget_remaining(self, chat, mock_db):
        """'How much budget remaining?' should check overall budget."""
        mock_db.get_all_budgets.return_value = [
            {"category": "groceries", "amount": 5000.00},
            {"category": "medical", "amount": 8000.00},
        ]
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "groceries", "total_debits": -4500.00},
            {"category": "medical", "total_debits": -7000.00},
        ]

        response, transactions, _ = chat.ask("How much budget remaining?")

        # Budget queries don't return transactions
        assert transactions == []
        mock_db.get_all_budgets.assert_called()

    def test_specific_category_budget_when_set(self, chat, mock_db):
        """'What's my medical budget?' should return that category's budget."""
        mock_db.get_all_budgets.return_value = [
            {"category": "medical", "amount": 8000.00},
        ]
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "medical", "total_debits": -7500.00},
        ]

        response, transactions, _ = chat.ask("What's my medical budget?")

        assert transactions == []
        mock_db.get_all_budgets.assert_called()

    def test_groceries_budget_when_not_set(self, chat, mock_db):
        """'What's my groceries budget?' when not set should indicate no budget."""
        mock_db.get_all_budgets.return_value = []  # No budgets set

        response, transactions, _ = chat.ask("What's my groceries budget?")

        # Should still work, LLM will say no budget set
        assert transactions == []


class TestBudgetManagement:
    """Test budget set/update/delete operations."""

    def test_set_groceries_budget(self, chat, mock_db):
        """'Set groceries budget to R5000' should create budget."""
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "groceries", "total_debits": -3000.00},
        ]

        response, transactions, _ = chat.ask("Set groceries budget to R5000")

        mock_db.upsert_budget.assert_called_once_with("groceries", 5000.0)
        assert "5,000" in response or "5000" in response
        assert transactions == []

    def test_remove_groceries_budget(self, chat, mock_db):
        """'remove groceries budget' should delete budget."""
        mock_db.delete_budget.return_value = True

        response, transactions, _ = chat.ask("remove groceries budget")

        mock_db.delete_budget.assert_called_once_with("groceries")
        assert "deleted" in response.lower()
        assert transactions == []

    def test_budget_workflow(self, chat, mock_db):
        """Test full budget workflow: check -> set -> remove -> check."""
        # Initial check - no budget
        mock_db.get_all_budgets.return_value = []
        response1, txs1, _ = chat.ask("What's my groceries budget?")
        assert txs1 == []

        # Set budget
        mock_db.get_category_summary_for_statement.return_value = []
        response2, txs2, _ = chat.ask("Set groceries budget to R5000")
        mock_db.upsert_budget.assert_called_with("groceries", 5000.0)
        assert txs2 == []

        # Remove budget
        mock_db.delete_budget.return_value = True
        response3, txs3, _ = chat.ask("remove groceries budget")
        mock_db.delete_budget.assert_called_with("groceries")
        assert txs3 == []


class TestDescriptionFiltering:
    """Test queries that filter by description within a category."""

    def test_roof_repairs_filters_home_maintenance(self, chat, mock_db):
        """'How much did I spend on roof repairs?' should filter home_maintenance."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-03-01", "description": "Roof repair specialist", "amount": -5000.00,
             "category": "home_maintenance", "transaction_type": "debit"},
            {"date": "2025-04-01", "description": "Pool cleaning service", "amount": -800.00,
             "category": "home_maintenance", "transaction_type": "debit"},
            {"date": "2025-05-01", "description": "Ceiling and roof work", "amount": -3000.00,
             "category": "home_maintenance", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("How much did I spend on roof repairs?")

        # Should only return transactions with "roof" in description
        assert len(transactions) == 2
        assert all("roof" in tx["description"].lower() for tx in transactions)

    def test_ceiling_repairs_filters_home_maintenance(self, chat, mock_db):
        """'How much did I spend on ceiling repairs?' should filter home_maintenance."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-03-01", "description": "Ceiling repairs", "amount": -2000.00,
             "category": "home_maintenance", "transaction_type": "debit"},
            {"date": "2025-04-01", "description": "Pool service", "amount": -800.00,
             "category": "home_maintenance", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("How much did I spend on ceiling repairs?")

        # Should only return transactions with "ceiling" in description
        assert len(transactions) == 1
        assert "ceiling" in transactions[0]["description"].lower()


class TestFloristQueries:
    """Test florist/flower queries."""

    def test_flowers_maps_to_florist(self, chat, mock_db):
        """'When did I buy my fiance flowers?' should search florist category."""
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-02-14", "description": "Netflorist Valentine", "amount": -500.00,
             "category": "florist", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("When did I buy my fiance flowers?")

        mock_db.get_transactions_by_category.assert_called_with("florist")
        assert len(transactions) == 1


class TestTypoCorrection:
    """Test that typos are corrected properly."""

    def test_chanel_smith_not_corrected_to_chase(self, chat, mock_db):
        """'List Chanel Smith payments' should NOT match 'chase' in 'Purchase'."""
        # LLM might return "chase" but validation should reject it
        chat._client.chat.completions.create.return_value = mock_openai_response("Chase")

        # No transactions match "Chanel Smith"
        mock_db.search_transactions.return_value = []

        response, transactions, _ = chat.ask("List Chanel Smith payments")

        # Should return empty, not 1000+ "Purchase" transactions
        assert len(transactions) == 0

    def test_sportify_corrected_to_spotify(self, chat, mock_db):
        """'when did the sportify price increase?' should correct to spotify."""
        # LLM returns correction
        chat._client.chat.completions.create.return_value = mock_openai_response("Spotify")

        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Spotify Premium", "amount": -99.99,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-06-22", "description": "Spotify Premium", "amount": -119.99,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("when did the sportify price increase?")

        assert len(transactions) == 2

    def test_metaflix_corrected_to_netflix_via_arrow(self, chat, mock_db):
        """'How much did I spent on Metaflix?' should correct to Netflix."""
        # LLM returns "Metaflix -> Netflix" format
        chat._client.chat.completions.create.return_value = mock_openai_response("Metaflix -> Netflix")

        netflix_result = [
            {"date": "2025-01-22", "description": "Netflix.com", "amount": -199.00,
             "category": "subscriptions", "transaction_type": "debit"},
        ]
        # 1) proper noun "metaflix" → no results
        # 2) simple term "metaflix" → no results
        # 3) LLM corrects to "netflix" → found
        mock_db.search_transactions.side_effect = [
            [],  # "metaflix" (proper noun detection)
            [],  # "metaflix" (simple terms, fast path)
            netflix_result,  # "netflix" (LLM correction)
        ]

        response, transactions, _ = chat.ask("How much did I spent on Metaflix?")

        # Should find Netflix transactions via LLM correction
        mock_db.search_transactions.assert_called_with("netflix")
        assert len(transactions) == 1


class TestHyphenVariations:
    """Test hyphen variations in search terms."""

    def test_xray_finds_x_ray(self, chat, mock_db):
        """'Show xray transactions' should also search for 'x-ray'."""
        # Search order: "xray transactions" (phrase), "xray" (term), "x-ray" (variation)
        mock_db.search_transactions.side_effect = [
            [],  # "xray transactions" - phrase search, no results
            [],  # "xray" - no results
            [{"date": "2025-03-15", "description": "X-Ray Diagnostics", "amount": -1500.00,
              "category": "medical", "transaction_type": "debit"}],  # "x-ray" - found
        ]

        response, transactions, _ = chat.ask("Show xray transactions")

        # Should have tried "x-ray" variation
        calls = [call[0][0] for call in mock_db.search_transactions.call_args_list]
        assert "x-ray" in calls
        assert len(transactions) == 1


class TestSingleTransactionQueries:
    """Test queries about specific single transactions."""

    def test_did_i_pay_paul(self, chat, mock_db):
        """'Did I pay Paul?' should find Paul transactions."""
        mock_db.search_transactions.return_value = [
            {"date": "2025-01-15", "description": "Payment to Paul", "amount": -500.00,
             "category": "transfer", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("Did I pay Paul?")

        assert len(transactions) == 1
        mock_db.search_transactions.assert_called()


class TestSubscriptionQueries:
    """Test subscription-related queries."""

    def test_spotify_spending(self, chat, mock_db):
        """'How much did I spend on spotify?' should find Spotify transactions."""
        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Spotify Premium", "amount": -119.99,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-02-22", "description": "Spotify Premium", "amount": -119.99,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("How much did I spend on spotify?")

        assert len(transactions) == 2


class TestPriceChangeDetection:
    """Test price change detection for subscriptions."""

    def test_netflix_price_increase_detected(self, chat, mock_db):
        """'When did the Metaflix price increase?' should detect Netflix price change."""
        chat._client.chat.completions.create.return_value = mock_openai_response("Metaflix -> Netflix")

        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Netflix.com", "amount": 199.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-02-22", "description": "Netflix.com", "amount": 199.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-06-22", "description": "Netflix.com", "amount": 229.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-07-22", "description": "Netflix.com", "amount": 229.00,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("When did the Metaflix price increase?")

        # Response should be deterministic (bypasses LLM)
        assert "Netflix" in response
        assert "increased" in response
        assert "June 2025" in response
        assert "199" in response
        assert "229" in response
        assert len(transactions) == 4

    def test_price_change_bypasses_llm(self, chat, mock_db):
        """Price change queries should return deterministic response without LLM."""
        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Spotify Premium", "amount": 99.99,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-06-22", "description": "Spotify Premium", "amount": 119.99,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        # LLM should not be called for the response (only for search term extraction)
        response, transactions, _ = chat.ask("When did spotify price increase?")

        # Response format is deterministic
        assert "Spotify" in response
        assert "increased" in response
        assert "June 2025" in response
        assert "99.99" in response
        assert "119.99" in response

    def test_price_no_change_deterministic(self, chat, mock_db):
        """No price change should return deterministic 'stayed the same' response."""
        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Netflix.com", "amount": 199.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-06-22", "description": "Netflix.com", "amount": 199.00,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("When did netflix price change?")

        assert "stayed the same" in response
        assert "Netflix" in response

    def test_price_change_uses_absolute_values(self, chat):
        """Price change detection should work with negative debit amounts."""
        transactions = [
            {"date": "2025-01-22", "amount": -199.00, "category": "subscriptions"},
            {"date": "2025-06-22", "amount": -229.00, "category": "subscriptions"},
        ]

        result = chat._detect_price_change(transactions)

        assert result is not None
        assert "INCREASED" in result
        assert "199" in result
        assert "229" in result


class TestMerchantNameExtraction:
    """Test merchant name extraction from transactions."""

    def test_extract_netflix(self, chat):
        """Should extract 'Netflix' from transaction description."""
        transactions = [{"description": "POS Purchase Netflix.Com 400738*9154"}]
        assert chat._extract_merchant_name(transactions) == "Netflix"

    def test_extract_spotify(self, chat):
        """Should extract 'Spotify' from transaction description."""
        transactions = [{"description": "Spotify Premium Monthly"}]
        assert chat._extract_merchant_name(transactions) == "Spotify"

    def test_extract_unknown_merchant(self, chat):
        """Should extract first meaningful word for unknown merchants."""
        transactions = [{"description": "ACME Corporation Payment"}]
        assert chat._extract_merchant_name(transactions) == "ACME"

    def test_empty_transactions(self, chat):
        """Should return default for empty transactions."""
        assert chat._extract_merchant_name([]) == "this service"

    def test_all_excluded_words_returns_default(self, chat):
        """Should return 'this service' when all words are excluded or short."""
        # All words are either short (<=3 chars) or in excluded list
        transactions = [{"description": "POS Purchase Payment"}]
        assert chat._extract_merchant_name(transactions) == "this service"

    def test_only_short_words_returns_default(self, chat):
        """Should return 'this service' when all words are too short."""
        transactions = [{"description": "A to B"}]
        assert chat._extract_merchant_name(transactions) == "this service"


class TestPriceDecrease:
    """Test price decrease detection and response."""

    def test_price_decrease_detected(self, chat, mock_db):
        """Price decrease should return deterministic response."""
        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Netflix.com", "amount": 229.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-06-22", "description": "Netflix.com", "amount": 199.00,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        response, transactions, _ = chat.ask("When did netflix price change?")

        assert "Netflix" in response
        assert "decreased" in response
        assert "June 2025" in response
        assert "229" in response
        assert "199" in response

    def test_price_decrease_detection_function(self, chat):
        """_detect_price_change should detect price decreases."""
        transactions = [
            {"date": "2025-01-22", "amount": 229.00, "category": "subscriptions"},
            {"date": "2025-06-22", "amount": 199.00, "category": "subscriptions"},
        ]

        result = chat._detect_price_change(transactions)

        assert result is not None
        assert "DECREASED" in result
        assert "229" in result
        assert "199" in result


class TestProperNounSearch:
    """Test proper noun detection and phrase search in _find_relevant_transactions."""

    def test_multi_word_proper_noun_finds_transactions(self, chat, mock_db):
        """'List Chanel Smith payments' should search 'chanel smith' as a phrase."""
        smith_txs = [
            {"date": "2025-12-01", "description": "FNB App Payment To Chanel Smith",
             "amount": -500.00, "category": "eft_payment", "transaction_type": "debit"},
            {"date": "2025-11-15", "description": "Send Money App Dr Send Chanel Smith",
             "amount": -200.00, "category": "ewallet", "transaction_type": "debit"},
        ]
        mock_db.search_transactions.return_value = smith_txs

        _, transactions, _ = chat.ask("List Chanel Smith payments")

        mock_db.search_transactions.assert_called_with("chanel smith")
        assert len(transactions) == 2
        assert transactions[0]["description"] == "FNB App Payment To Chanel Smith"

    def test_multi_word_proper_noun_filters_fees(self, chat, mock_db):
        """Proper noun phrase search should filter out fee transactions."""
        results_with_fees = [
            {"date": "2025-12-01", "description": "FNB App Payment To Chanel Smith",
             "amount": -500.00, "category": "eft_payment", "transaction_type": "debit"},
            {"date": "2025-12-02", "description": "#Service Fees Chanel Smith",
             "amount": -5.00, "category": "fees", "transaction_type": "debit"},
        ]
        mock_db.search_transactions.return_value = results_with_fees

        _, transactions, _ = chat.ask("List Chanel Smith payments")

        assert len(transactions) == 1
        assert transactions[0]["category"] == "eft_payment"


class TestExtractSearchTermsSingleWord:
    """Test _extract_search_terms returning a single LLM word found in the query."""

    def test_llm_single_word_match(self, chat, mock_db):
        """LLM returning a single word present in query should use that term."""
        # Use lowercase query so no proper nouns are detected,
        # forcing the code into _extract_search_terms → single word LLM path
        chat._client.chat.completions.create.return_value = mock_openai_response("spotify")

        mock_db.search_transactions.return_value = [
            {"date": "2025-12-29", "description": "POS Purchase Spotifyza",
             "amount": -119.99, "category": "subscriptions", "transaction_type": "debit"},
        ]

        _, transactions, _ = chat.ask("show me spotify payments")

        mock_db.search_transactions.assert_called_with("spotify")
        assert len(transactions) == 1


class TestBuildContextNoBudget:
    """Test _build_context detecting a category with no budget set."""

    def test_no_budget_set_for_category_adds_context(self, chat, mock_db):
        """Budget query for a category without a budget should add NO BUDGET SET context."""
        mock_db.get_all_budgets.return_value = [
            {"category": "medical", "amount": 8000.00},
        ]
        mock_db.get_latest_statement.return_value = {"statement_number": 288, "statement_date": "2025-12-31"}
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "medical", "total_debits": -7000.00},
        ]

        context = chat._build_context([], "What's my groceries budget?")

        assert "NO BUDGET SET for groceries" in context


class TestHistoryAlternation:
    """Test conversation history alternation fix."""

    def test_history_strips_leading_assistant_message(self, chat, mock_db):
        """When [-10:] slice starts with assistant, it should be stripped."""
        # Fill history with 5 complete exchanges (10 entries).
        # _get_llm_response appends 1 user message internally → 11 total.
        # [-10:] on 11 entries starts at index 1 (assistant0), triggering the fix.
        for i in range(5):
            chat._conversation_history.append({"role": "user", "content": f"Q{i}"})
            chat._conversation_history.append({"role": "assistant", "content": f"A{i}"})

        response = chat._get_llm_response("test", "test context")

        # Verify LLM was called with properly alternating messages
        call_args = chat._client.chat.completions.create.call_args
        messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
        # First message is system, second must be user (not assistant)
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestDeterministicBudgetResponses:
    """Test deterministic budget responses in ask()."""

    def test_specific_category_over_budget(self, chat, mock_db):
        """Specific category budget query when over budget."""
        mock_db.get_all_budgets.return_value = [
            {"category": "medical", "amount": 8000.00},
        ]
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "medical", "total_debits": -8615.00},
        ]
        mock_db.get_transactions_by_statement.return_value = [
            {"date": "2025-12-15", "description": "Doctor visit", "amount": -1500.00,
             "category": "medical", "transaction_type": "debit"},
        ]

        response, transactions, stats = chat.ask("What's my medical budget?")

        assert "OVER BUDGET" in response
        assert "R8,000.00" in response
        assert "R8,615.00" in response
        assert stats is None  # Deterministic, no LLM
        assert len(transactions) == 1

    def test_specific_category_no_latest_statement(self, chat, mock_db):
        """Specific category budget without a latest statement falls back to get_transactions_by_category."""
        mock_db.get_all_budgets.return_value = [
            {"category": "groceries", "amount": 5000.00},
        ]
        mock_db.get_latest_statement.return_value = None
        mock_db.get_transactions_by_category.return_value = [
            {"date": "2025-12-01", "description": "Woolworths", "amount": -800.00,
             "category": "groceries", "transaction_type": "debit"},
        ]

        response, transactions, stats = chat.ask("What's my groceries budget?")

        mock_db.get_transactions_by_category.assert_called_with("groceries")
        assert "R5,000.00" in response
        assert len(transactions) == 1
        assert stats is None

    def test_specific_category_no_budget_set(self, chat, mock_db):
        """Asking about a category that exists but has no budget."""
        mock_db.get_all_budgets.return_value = [
            {"category": "medical", "amount": 8000.00},
        ]

        response, transactions, stats = chat.ask("What's my groceries budget?")

        assert "haven't set a budget for groceries" in response
        assert transactions == []
        assert stats is None

    def test_overall_budget_over_budget(self, chat, mock_db):
        """Overall budget query when total spending exceeds total budget."""
        mock_db.get_all_budgets.return_value = [
            {"category": "groceries", "amount": 3000.00},
            {"category": "medical", "amount": 5000.00},
        ]
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "groceries", "total_debits": -4000.00},
            {"category": "medical", "total_debits": -6000.00},
        ]

        response, transactions, stats = chat.ask("How much budget remaining?")

        assert "OVER BUDGET" in response
        assert "R8,000.00" in response  # total budgeted
        assert "R10,000.00" in response  # total spent
        assert stats is None
