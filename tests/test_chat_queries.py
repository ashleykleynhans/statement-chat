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
        # Default LLM response
        mock_client.chat.completions.create.return_value = mock_openai_response("Test response")

        chat = ChatInterface(mock_db, host="localhost", port=1234, model="test-model")
        yield chat


class TestGreetings:
    """Test greeting handling."""

    def test_hi_returns_no_transactions(self, chat):
        """Greeting 'Hi' should return empty transactions."""
        response, transactions = chat.ask("Hi")
        assert transactions == []

    def test_hello_returns_no_transactions(self, chat):
        """Greeting 'Hello' should return empty transactions."""
        response, transactions = chat.ask("Hello")
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

        response, transactions = chat.ask("When last did I pay the doctor?")

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

        response, transactions = chat.ask("How much budget remaining?")

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

        response, transactions = chat.ask("What's my medical budget?")

        assert transactions == []
        mock_db.get_all_budgets.assert_called()

    def test_groceries_budget_when_not_set(self, chat, mock_db):
        """'What's my groceries budget?' when not set should indicate no budget."""
        mock_db.get_all_budgets.return_value = []  # No budgets set

        response, transactions = chat.ask("What's my groceries budget?")

        # Should still work, LLM will say no budget set
        assert transactions == []


class TestBudgetManagement:
    """Test budget set/update/delete operations."""

    def test_set_groceries_budget(self, chat, mock_db):
        """'Set groceries budget to R5000' should create budget."""
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "groceries", "total_debits": -3000.00},
        ]

        response, transactions = chat.ask("Set groceries budget to R5000")

        mock_db.upsert_budget.assert_called_once_with("groceries", 5000.0)
        assert "5,000" in response or "5000" in response
        assert transactions == []

    def test_remove_groceries_budget(self, chat, mock_db):
        """'remove groceries budget' should delete budget."""
        mock_db.delete_budget.return_value = True

        response, transactions = chat.ask("remove groceries budget")

        mock_db.delete_budget.assert_called_once_with("groceries")
        assert "deleted" in response.lower()
        assert transactions == []

    def test_budget_workflow(self, chat, mock_db):
        """Test full budget workflow: check -> set -> remove -> check."""
        # Initial check - no budget
        mock_db.get_all_budgets.return_value = []
        response1, txs1 = chat.ask("What's my groceries budget?")
        assert txs1 == []

        # Set budget
        mock_db.get_category_summary_for_statement.return_value = []
        response2, txs2 = chat.ask("Set groceries budget to R5000")
        mock_db.upsert_budget.assert_called_with("groceries", 5000.0)
        assert txs2 == []

        # Remove budget
        mock_db.delete_budget.return_value = True
        response3, txs3 = chat.ask("remove groceries budget")
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

        response, transactions = chat.ask("How much did I spend on roof repairs?")

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

        response, transactions = chat.ask("How much did I spend on ceiling repairs?")

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

        response, transactions = chat.ask("When did I buy my fiance flowers?")

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

        response, transactions = chat.ask("List Chanel Smith payments")

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

        response, transactions = chat.ask("when did the sportify price increase?")

        assert len(transactions) == 2

    def test_metaflix_corrected_to_netflix_via_arrow(self, chat, mock_db):
        """'How much did I spent on Metaflix?' should correct to Netflix."""
        # LLM returns "Metaflix -> Netflix" format
        chat._client.chat.completions.create.return_value = mock_openai_response("Metaflix -> Netflix")

        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Netflix.com", "amount": -199.00,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        response, transactions = chat.ask("How much did I spent on Metaflix?")

        # Should find Netflix transactions
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

        response, transactions = chat.ask("Show xray transactions")

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

        response, transactions = chat.ask("Did I pay Paul?")

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

        response, transactions = chat.ask("How much did I spend on spotify?")

        assert len(transactions) == 2


class TestPriceChangeDetection:
    """Test price change detection for subscriptions."""

    def test_netflix_price_increase_detected(self, chat, mock_db):
        """'When did the Metaflix price increase?' should detect Netflix price change."""
        chat._client.chat.completions.create.return_value = mock_openai_response("Metaflix -> Netflix")

        mock_db.search_transactions.return_value = [
            {"date": "2025-01-22", "description": "Netflix.com", "amount": -199.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-02-22", "description": "Netflix.com", "amount": -199.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-06-22", "description": "Netflix.com", "amount": -229.00,
             "category": "subscriptions", "transaction_type": "debit"},
            {"date": "2025-07-22", "description": "Netflix.com", "amount": -229.00,
             "category": "subscriptions", "transaction_type": "debit"},
        ]

        response, transactions = chat.ask("When did the Metaflix price increase?")

        assert len(transactions) == 4
        # Price change should be detected in the context building
        price_change = chat._detect_price_change(transactions)
        assert price_change is not None
        assert "INCREASED" in price_change
        assert "June 2025" in price_change
        assert "199" in price_change
        assert "229" in price_change

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
