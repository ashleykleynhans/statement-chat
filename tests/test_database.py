"""Tests for database module."""

import pytest
from pathlib import Path

from src.database import Database


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test.db"
    return Database(db_path)


@pytest.fixture
def db_with_data(db):
    """Create a database with sample data."""
    stmt_id = db.insert_statement("test.pdf", "12345678901", "2025-01-01")
    db.insert_transaction(
        statement_id=stmt_id,
        date="2025-01-15",
        description="Woolworths Groceries",
        amount=500.00,
        balance=1000.00,
        transaction_type="debit",
        category="groceries",
    )
    db.insert_transaction(
        statement_id=stmt_id,
        date="2025-01-16",
        description="Salary Payment",
        amount=10000.00,
        balance=11000.00,
        transaction_type="credit",
        category="salary",
    )
    db.insert_transaction(
        statement_id=stmt_id,
        date="2025-01-17",
        description="Shell Fuel",
        amount=800.00,
        balance=10200.00,
        transaction_type="debit",
        category="fuel",
    )
    return db


class TestDatabaseInit:
    """Tests for Database initialization."""

    def test_creates_db_file(self, tmp_path):
        """Test database file is created."""
        db_path = tmp_path / "test.db"
        Database(db_path)
        assert db_path.exists()

    def test_creates_parent_dirs(self, tmp_path):
        """Test parent directories are created."""
        db_path = tmp_path / "subdir" / "nested" / "test.db"
        Database(db_path)
        assert db_path.exists()

    def test_schema_created(self, db):
        """Test tables are created."""
        conn = db._get_connection()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t["name"] for t in tables]
        assert "statements" in table_names
        assert "transactions" in table_names


class TestStatements:
    """Tests for statement operations."""

    def test_insert_statement(self, db):
        """Test inserting a statement."""
        stmt_id = db.insert_statement("test.pdf", "12345678901", "2025-01-01")
        assert stmt_id == 1

    def test_statement_exists(self, db):
        """Test checking if statement exists."""
        assert not db.statement_exists("test.pdf")
        db.insert_statement("test.pdf")
        assert db.statement_exists("test.pdf")

    def test_duplicate_statement_raises(self, db):
        """Test inserting duplicate statement raises error."""
        db.insert_statement("test.pdf")
        with pytest.raises(Exception):
            db.insert_statement("test.pdf")


class TestTransactions:
    """Tests for transaction operations."""

    def test_insert_transaction(self, db):
        """Test inserting a transaction."""
        stmt_id = db.insert_statement("test.pdf")
        tx_id = db.insert_transaction(
            statement_id=stmt_id,
            date="2025-01-15",
            description="Test transaction",
            amount=100.00,
        )
        assert tx_id == 1

    def test_insert_transactions_batch(self, db):
        """Test batch inserting transactions."""
        stmt_id = db.insert_statement("test.pdf")
        transactions = [
            {"date": "2025-01-15", "description": "Tx 1", "amount": 100},
            {"date": "2025-01-16", "description": "Tx 2", "amount": 200},
            {"date": "2025-01-17", "description": "Tx 3", "amount": 300},
        ]
        db.insert_transactions_batch(stmt_id, transactions)

        all_tx = db.get_all_transactions()
        assert len(all_tx) == 3

    def test_get_all_transactions(self, db_with_data):
        """Test getting all transactions."""
        transactions = db_with_data.get_all_transactions()
        assert len(transactions) == 3

    def test_get_all_transactions_with_limit(self, db_with_data):
        """Test getting transactions with limit."""
        transactions = db_with_data.get_all_transactions(limit=2)
        assert len(transactions) == 2

    def test_get_transactions_by_category(self, db_with_data):
        """Test filtering by category."""
        groceries = db_with_data.get_transactions_by_category("groceries")
        assert len(groceries) == 1
        assert groceries[0]["description"] == "Woolworths Groceries"

    def test_get_transactions_by_type(self, db_with_data):
        """Test filtering by transaction type."""
        debits = db_with_data.get_transactions_by_type("debit")
        credits = db_with_data.get_transactions_by_type("credit")
        assert len(debits) == 2
        assert len(credits) == 1

    def test_search_transactions(self, db_with_data):
        """Test searching transactions."""
        results = db_with_data.search_transactions("Woolworths")
        assert len(results) == 1
        assert results[0]["category"] == "groceries"

    def test_search_transactions_case_insensitive(self, db_with_data):
        """Test search is case-insensitive."""
        results = db_with_data.search_transactions("woolworths")
        assert len(results) == 1

    def test_get_transactions_in_date_range(self, db_with_data):
        """Test getting transactions by date range."""
        results = db_with_data.get_transactions_in_date_range(
            "2025-01-15", "2025-01-16"
        )
        assert len(results) == 2

    def test_get_unclassified_transactions(self, db):
        """Test getting unclassified transactions."""
        stmt_id = db.insert_statement("test.pdf")
        db.insert_transaction(stmt_id, "2025-01-15", "Unclassified", 100)
        db.insert_transaction(
            stmt_id, "2025-01-16", "Classified", 200, category="other"
        )

        unclassified = db.get_unclassified_transactions()
        assert len(unclassified) == 1
        assert unclassified[0]["description"] == "Unclassified"

    def test_update_transaction_classification(self, db):
        """Test updating transaction classification."""
        stmt_id = db.insert_statement("test.pdf")
        tx_id = db.insert_transaction(stmt_id, "2025-01-15", "Test", 100)

        db.update_transaction_classification(tx_id, "groceries", "Woolworths")

        transactions = db.get_all_transactions()
        assert transactions[0]["category"] == "groceries"
        assert transactions[0]["recipient_or_payer"] == "Woolworths"


class TestAggregations:
    """Tests for aggregation queries."""

    def test_get_category_summary(self, db_with_data):
        """Test getting category summary."""
        summary = db_with_data.get_category_summary()
        assert len(summary) == 3

        groceries = next(s for s in summary if s["category"] == "groceries")
        assert groceries["count"] == 1
        assert groceries["total_debits"] == 500.00

    def test_get_all_categories(self, db_with_data):
        """Test getting all categories."""
        categories = db_with_data.get_all_categories()
        assert set(categories) == {"groceries", "salary", "fuel"}

    def test_get_stats(self, db_with_data):
        """Test getting database stats."""
        stats = db_with_data.get_stats()
        assert stats["total_statements"] == 1
        assert stats["total_transactions"] == 3
        assert stats["total_debits"] == 1300.00
        assert stats["total_credits"] == 10000.00
        assert stats["categories_count"] == 3
