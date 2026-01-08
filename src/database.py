"""SQLite database operations for bank statement storage."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class Database:
    """SQLite database manager for bank statements and transactions."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """Initialize database schema if not exists."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS statements (
                    id INTEGER PRIMARY KEY,
                    filename TEXT UNIQUE NOT NULL,
                    account_number TEXT,
                    statement_date DATE,
                    statement_number TEXT,
                    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY,
                    statement_id INTEGER REFERENCES statements(id),
                    date DATE NOT NULL,
                    description TEXT NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    balance DECIMAL(10,2),
                    transaction_type TEXT CHECK(transaction_type IN ('debit', 'credit')),
                    category TEXT,
                    recipient_or_payer TEXT,
                    reference TEXT,
                    raw_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_transactions_date
                    ON transactions(date);
                CREATE INDEX IF NOT EXISTS idx_transactions_category
                    ON transactions(category);
                CREATE INDEX IF NOT EXISTS idx_transactions_type
                    ON transactions(transaction_type);

                CREATE TABLE IF NOT EXISTS budgets (
                    id INTEGER PRIMARY KEY,
                    category TEXT UNIQUE NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Migration: Add statement_number column if missing (for existing databases)
            cursor = conn.execute("PRAGMA table_info(statements)")
            columns = [row[1] for row in cursor.fetchall()]
            if "statement_number" not in columns:
                conn.execute("ALTER TABLE statements ADD COLUMN statement_number TEXT")

    def statement_exists(self, filename: str) -> bool:
        """Check if a statement has already been imported."""
        with self._get_connection() as conn:
            result = conn.execute(
                "SELECT 1 FROM statements WHERE filename = ?",
                (filename,)
            ).fetchone()
            return result is not None

    def insert_statement(
        self,
        filename: str,
        account_number: str | None = None,
        statement_date: str | None = None,
        statement_number: str | None = None
    ) -> int:
        """Insert a new statement record and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO statements (filename, account_number, statement_date, statement_number)
                   VALUES (?, ?, ?, ?)""",
                (filename, account_number, statement_date, statement_number)
            )
            return cursor.lastrowid

    def insert_transaction(
        self,
        statement_id: int,
        date: str,
        description: str,
        amount: float,
        balance: float | None = None,
        transaction_type: str | None = None,
        category: str | None = None,
        recipient_or_payer: str | None = None,
        reference: str | None = None,
        raw_text: str | None = None
    ) -> int:
        """Insert a new transaction record and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO transactions
                   (statement_id, date, description, amount, balance,
                    transaction_type, category, recipient_or_payer, reference, raw_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (statement_id, date, description, amount, balance,
                 transaction_type, category, recipient_or_payer, reference, raw_text)
            )
            return cursor.lastrowid

    def insert_transactions_batch(
        self,
        statement_id: int,
        transactions: list[dict]
    ) -> None:
        """Insert multiple transactions in a single batch."""
        with self._get_connection() as conn:
            conn.executemany(
                """INSERT INTO transactions
                   (statement_id, date, description, amount, balance,
                    transaction_type, category, recipient_or_payer, reference, raw_text)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (statement_id, t.get("date"), t.get("description"), t.get("amount"),
                     t.get("balance"), t.get("transaction_type"), t.get("category"),
                     t.get("recipient_or_payer"), t.get("reference"), t.get("raw_text"))
                    for t in transactions
                ]
            )

    def update_transaction_classification(
        self,
        transaction_id: int,
        category: str,
        recipient_or_payer: str | None = None
    ) -> None:
        """Update classification for a transaction."""
        with self._get_connection() as conn:
            conn.execute(
                """UPDATE transactions
                   SET category = ?, recipient_or_payer = ?
                   WHERE id = ?""",
                (category, recipient_or_payer, transaction_id)
            )

    def get_unclassified_transactions(self) -> list[dict]:
        """Get all transactions without a category."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT id, date, description, amount, transaction_type, raw_text
                   FROM transactions WHERE category IS NULL"""
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_transactions(
        self,
        limit: int | None = None,
        offset: int = 0
    ) -> list[dict]:
        """Get all transactions with optional pagination."""
        query = """
            SELECT t.*, s.filename, s.account_number, s.statement_number
            FROM transactions t
            JOIN statements s ON t.statement_id = s.id
            ORDER BY t.date DESC
        """
        if limit:
            query += f" LIMIT {limit} OFFSET {offset}"

        with self._get_connection() as conn:
            rows = conn.execute(query).fetchall()
            return [dict(row) for row in rows]

    def get_transactions_by_category(self, category: str) -> list[dict]:
        """Get all transactions in a specific category."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT t.*, s.filename, s.account_number, s.statement_number
                   FROM transactions t
                   JOIN statements s ON t.statement_id = s.id
                   WHERE t.category = ?
                   ORDER BY t.date DESC""",
                (category,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_transactions_by_type(self, transaction_type: str) -> list[dict]:
        """Get all debits or credits."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT t.*, s.filename, s.account_number, s.statement_number
                   FROM transactions t
                   JOIN statements s ON t.statement_id = s.id
                   WHERE t.transaction_type = ?
                   ORDER BY t.date DESC""",
                (transaction_type,)
            ).fetchall()
            return [dict(row) for row in rows]

    def search_transactions(self, search_term: str) -> list[dict]:
        """Search transactions by description or recipient."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT t.*, s.filename, s.account_number, s.statement_number
                   FROM transactions t
                   JOIN statements s ON t.statement_id = s.id
                   WHERE t.description LIKE ?
                      OR t.recipient_or_payer LIKE ?
                      OR t.raw_text LIKE ?
                   ORDER BY t.date DESC""",
                (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%")
            ).fetchall()
            return [dict(row) for row in rows]

    def get_transactions_in_date_range(
        self,
        start_date: str,
        end_date: str
    ) -> list[dict]:
        """Get transactions within a date range."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT t.*, s.filename, s.account_number, s.statement_number
                   FROM transactions t
                   JOIN statements s ON t.statement_id = s.id
                   WHERE t.date BETWEEN ? AND ?
                   ORDER BY t.date DESC""",
                (start_date, end_date)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_category_summary(self) -> list[dict]:
        """Get spending summary by category."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT category,
                          COUNT(*) as count,
                          SUM(CASE WHEN transaction_type = 'debit' THEN amount ELSE 0 END) as total_debits,
                          SUM(CASE WHEN transaction_type = 'credit' THEN amount ELSE 0 END) as total_credits
                   FROM transactions
                   GROUP BY category
                   ORDER BY total_debits DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

    def get_all_categories(self) -> list[str]:
        """Get list of all unique categories."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT DISTINCT category FROM transactions WHERE category IS NOT NULL"
            ).fetchall()
            return [row["category"] for row in rows]

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._get_connection() as conn:
            stats = {}
            stats["total_statements"] = conn.execute(
                "SELECT COUNT(*) FROM statements"
            ).fetchone()[0]
            stats["total_transactions"] = conn.execute(
                "SELECT COUNT(*) FROM transactions"
            ).fetchone()[0]
            stats["total_debits"] = conn.execute(
                "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'debit'"
            ).fetchone()[0] or 0
            stats["total_credits"] = conn.execute(
                "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'credit'"
            ).fetchone()[0] or 0
            stats["categories_count"] = conn.execute(
                "SELECT COUNT(DISTINCT category) FROM transactions"
            ).fetchone()[0]
            return stats

    def get_all_statements(self) -> list[dict]:
        """Get all statements ordered by date descending."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT id, filename, account_number, statement_date, statement_number
                   FROM statements
                   ORDER BY statement_date DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

    def get_latest_statement(self) -> dict | None:
        """Get the most recent statement."""
        with self._get_connection() as conn:
            row = conn.execute(
                """SELECT id, filename, account_number, statement_date, statement_number
                   FROM statements
                   ORDER BY statement_date DESC
                   LIMIT 1"""
            ).fetchone()
            return dict(row) if row else None

    def get_transactions_by_statement(self, statement_number: str) -> list[dict]:
        """Get all transactions for a specific statement."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT t.*, s.filename, s.account_number, s.statement_number
                   FROM transactions t
                   JOIN statements s ON t.statement_id = s.id
                   WHERE s.statement_number = ?
                   ORDER BY t.date DESC""",
                (statement_number,)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_category_summary_for_statement(self, statement_number: str) -> list[dict]:
        """Get spending summary by category for a specific statement."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """SELECT category,
                          COUNT(*) as count,
                          SUM(CASE WHEN transaction_type = 'debit' THEN amount ELSE 0 END) as total_debits,
                          SUM(CASE WHEN transaction_type = 'credit' THEN amount ELSE 0 END) as total_credits
                   FROM transactions t
                   JOIN statements s ON t.statement_id = s.id
                   WHERE s.statement_number = ?
                   GROUP BY category
                   ORDER BY total_debits DESC""",
                (statement_number,)
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_budget(self, category: str, amount: float) -> int:
        """Insert or update a budget for a category."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO budgets (category, amount, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(category) DO UPDATE SET
                       amount = excluded.amount,
                       updated_at = CURRENT_TIMESTAMP""",
                (category, amount)
            )
            return cursor.lastrowid

    def get_all_budgets(self) -> list[dict]:
        """Get all budget entries."""
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT id, category, amount FROM budgets ORDER BY category"
            ).fetchall()
            return [dict(row) for row in rows]

    def get_budget_by_category(self, category: str) -> dict | None:
        """Get budget for a specific category."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT id, category, amount FROM budgets WHERE category = ?",
                (category,)
            ).fetchone()
            return dict(row) if row else None

    def delete_budget(self, category: str) -> bool:
        """Delete a budget by category. Returns True if deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM budgets WHERE category = ?",
                (category,)
            )
            return cursor.rowcount > 0
