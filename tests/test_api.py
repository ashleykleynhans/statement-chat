"""Tests for API module."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.session import SessionManager, ChatSession
from src.api.models import StatsResponse, CategoriesListResponse


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = Mock()
    db.get_stats.return_value = {
        "total_statements": 5,
        "total_transactions": 100,
        "total_debits": 50000.00,
        "total_credits": 75000.00,
        "categories_count": 10,
    }
    db.get_all_categories.return_value = ["groceries", "fuel", "salary", None]
    db.get_category_summary.return_value = [
        {"category": "groceries", "count": 20, "total_debits": 5000.00, "total_credits": 0.00},
        {"category": "fuel", "count": 10, "total_debits": 2000.00, "total_credits": 0.00},
    ]
    db.get_all_transactions.return_value = [
        {
            "id": 1,
            "date": "2025-01-15",
            "description": "Woolworths",
            "amount": 500.00,
            "balance": 10000.00,
            "transaction_type": "debit",
            "category": "groceries",
            "recipient_or_payer": "Woolworths",
            "reference": None,
        }
    ]
    db.search_transactions.return_value = [
        {"id": 1, "description": "Woolworths", "amount": 500.00}
    ]
    db.get_transactions_by_category.return_value = [
        {"id": 1, "description": "Woolworths", "amount": 500.00, "category": "groceries"}
    ]
    db.get_transactions_by_type.return_value = [
        {"id": 1, "description": "Salary", "amount": 10000.00, "transaction_type": "credit"}
    ]
    db.get_transactions_in_date_range.return_value = [
        {"id": 1, "description": "Test", "amount": 100.00, "date": "2025-01-15"}
    ]
    return db


@pytest.fixture
def mock_config():
    """Create mock config."""
    return {
        "llm": {
            "host": "localhost",
            "port": 11434,
            "model": "llama3.2",
        },
        "paths": {
            "database": "test.db",
        },
    }


@pytest.fixture
def client(mock_db, mock_config):
    """Create test client with mocked dependencies."""
    app = create_app()
    app.state.db = mock_db
    app.state.config = mock_config
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_check(self, client):
        """Test health endpoint returns healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "active_sessions" in data


class TestStatsEndpoints:
    """Tests for stats and categories endpoints."""

    def test_get_stats(self, client):
        """Test getting database statistics."""
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        data = response.json()
        assert data["total_statements"] == 5
        assert data["total_transactions"] == 100
        assert data["total_debits"] == 50000.00
        assert data["total_credits"] == 75000.00

    def test_list_categories(self, client):
        """Test listing categories."""
        response = client.get("/api/v1/categories")
        assert response.status_code == 200
        data = response.json()
        assert "groceries" in data["categories"]
        assert "fuel" in data["categories"]
        # None should be filtered out
        assert None not in data["categories"]

    def test_category_summary(self, client):
        """Test category spending summary."""
        response = client.get("/api/v1/categories/summary")
        assert response.status_code == 200
        data = response.json()
        assert len(data["categories"]) == 2
        assert data["categories"][0]["category"] == "groceries"
        assert data["categories"][0]["count"] == 20


class TestTransactionEndpoints:
    """Tests for transaction query endpoints."""

    def test_list_transactions(self, client, mock_db):
        """Test paginated transaction list."""
        response = client.get("/api/v1/transactions")
        assert response.status_code == 200
        data = response.json()
        assert len(data["transactions"]) == 1
        assert data["total"] == 100
        assert data["limit"] == 20
        assert data["offset"] == 0

    def test_list_transactions_with_pagination(self, client, mock_db):
        """Test transaction list with custom pagination."""
        response = client.get("/api/v1/transactions?limit=10&offset=5")
        assert response.status_code == 200
        mock_db.get_all_transactions.assert_called_with(limit=10, offset=5)

    def test_search_transactions(self, client, mock_db):
        """Test transaction search."""
        response = client.get("/api/v1/transactions/search?q=woolworths")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        mock_db.search_transactions.assert_called_with("woolworths")

    def test_search_transactions_empty_query(self, client):
        """Test search with empty query returns error."""
        response = client.get("/api/v1/transactions/search?q=")
        assert response.status_code == 422  # Validation error

    def test_get_by_category(self, client, mock_db):
        """Test filtering by category."""
        response = client.get("/api/v1/transactions/category/groceries")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        mock_db.get_transactions_by_category.assert_called_with("groceries")

    def test_get_by_type_debit(self, client, mock_db):
        """Test filtering by debit type."""
        response = client.get("/api/v1/transactions/type/debit")
        assert response.status_code == 200
        mock_db.get_transactions_by_type.assert_called_with("debit")

    def test_get_by_type_credit(self, client, mock_db):
        """Test filtering by credit type."""
        response = client.get("/api/v1/transactions/type/credit")
        assert response.status_code == 200
        mock_db.get_transactions_by_type.assert_called_with("credit")

    def test_get_by_type_invalid(self, client):
        """Test invalid type returns error."""
        response = client.get("/api/v1/transactions/type/invalid")
        assert response.status_code == 400
        assert "debit" in response.json()["detail"]

    def test_get_by_date_range(self, client, mock_db):
        """Test date range filter."""
        response = client.get("/api/v1/transactions/date-range?start=2025-01-01&end=2025-01-31")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        mock_db.get_transactions_in_date_range.assert_called_with("2025-01-01", "2025-01-31")

    def test_get_by_date_range_invalid(self, client):
        """Test invalid date range returns error."""
        response = client.get("/api/v1/transactions/date-range?start=2025-01-31&end=2025-01-01")
        assert response.status_code == 400
        assert "before" in response.json()["detail"]

    def test_get_by_statement(self, client, mock_db):
        """Test filtering by statement number."""
        mock_db.get_transactions_by_statement.return_value = [
            {"id": 1, "description": "Test", "amount": 100}
        ]
        response = client.get("/api/v1/transactions/statement/123")
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 1
        mock_db.get_transactions_by_statement.assert_called_with("123")


class TestTransactionExport:
    """Tests for transaction CSV export endpoint."""

    def test_export_all_transactions(self, client, mock_db):
        """Test exporting all transactions."""
        mock_db.get_all_transactions.return_value = [
            {
                "id": 1,
                "date": "2025-01-15",
                "description": "Woolworths",
                "amount": 500.00,
                "transaction_type": "debit",
                "category": "groceries",
                "balance": 10000.00,
                "statement_number": "123",
                "reference": "REF001",
                "recipient_or_payer": "Woolworths Store",
            }
        ]

        response = client.get("/api/v1/transactions/export")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        assert "transactions_" in response.headers["content-disposition"]
        assert ".csv" in response.headers["content-disposition"]

        # Parse CSV content
        import csv
        import io

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)

        # Check header
        assert rows[0] == [
            "Date",
            "Description",
            "Amount",
            "Type",
            "Category",
            "Balance",
            "Statement",
            "Reference",
            "Recipient/Payer",
        ]
        # Check data row
        assert rows[1][0] == "2025-01-15"
        assert rows[1][1] == "Woolworths"
        assert rows[1][2] == "500.0"
        assert rows[1][3] == "debit"
        assert rows[1][4] == "groceries"

    def test_export_with_search(self, client, mock_db):
        """Test exporting with search query."""
        mock_db.search_transactions.return_value = [
            {
                "id": 1,
                "date": "2025-01-15",
                "description": "Woolworths",
                "amount": 500.00,
                "transaction_type": "debit",
                "category": "groceries",
            }
        ]

        response = client.get("/api/v1/transactions/export?q=woolworths")

        assert response.status_code == 200
        mock_db.search_transactions.assert_called_with("woolworths")

    def test_export_with_category(self, client, mock_db):
        """Test exporting with category filter."""
        mock_db.get_transactions_by_category.return_value = []

        response = client.get("/api/v1/transactions/export?category=groceries")

        assert response.status_code == 200
        mock_db.get_transactions_by_category.assert_called_with("groceries")

    def test_export_with_statement(self, client, mock_db):
        """Test exporting with statement filter."""
        mock_db.get_transactions_by_statement.return_value = []

        response = client.get("/api/v1/transactions/export?statement=287")

        assert response.status_code == 200
        mock_db.get_transactions_by_statement.assert_called_with("287")

    def test_export_with_date_range(self, client, mock_db):
        """Test exporting with date range filter."""
        mock_db.get_transactions_in_date_range.return_value = []

        response = client.get(
            "/api/v1/transactions/export?start_date=2025-01-01&end_date=2025-01-31"
        )

        assert response.status_code == 200
        mock_db.get_transactions_in_date_range.assert_called_with(
            "2025-01-01", "2025-01-31"
        )

    def test_export_invalid_date_range(self, client, mock_db):
        """Test export with invalid date range returns error."""
        response = client.get(
            "/api/v1/transactions/export?start_date=2025-01-31&end_date=2025-01-01"
        )

        assert response.status_code == 400
        assert "before" in response.json()["detail"]

    def test_export_empty_results(self, client, mock_db):
        """Test export with no matching transactions."""
        mock_db.search_transactions.return_value = []

        response = client.get("/api/v1/transactions/export?q=nonexistent")

        assert response.status_code == 200

        # Should still have header row
        import csv
        import io

        reader = csv.reader(io.StringIO(response.text))
        rows = list(reader)
        assert len(rows) == 1  # Header only


class TestSessionManager:
    """Tests for session management."""

    def test_create_session(self):
        """Test creating a new session."""
        manager = SessionManager()
        mock_db = Mock()

        with patch('src.api.session.ChatInterface') as mock_chat:
            session = manager.create_session(mock_db, "localhost", 11434, "llama3.2")

        assert session.session_id is not None
        assert manager.active_sessions == 1

    def test_get_session(self):
        """Test retrieving a session."""
        manager = SessionManager()
        mock_db = Mock()

        with patch('src.api.session.ChatInterface'):
            session = manager.create_session(mock_db, "localhost", 11434, "llama3.2")
            retrieved = manager.get_session(session.session_id)

        assert retrieved == session

    def test_get_nonexistent_session(self):
        """Test getting non-existent session returns None."""
        manager = SessionManager()
        assert manager.get_session("nonexistent") is None

    def test_remove_session(self):
        """Test removing a session."""
        manager = SessionManager()
        mock_db = Mock()

        with patch('src.api.session.ChatInterface'):
            session = manager.create_session(mock_db, "localhost", 11434, "llama3.2")
            manager.remove_session(session.session_id)

        assert manager.active_sessions == 0
        assert manager.get_session(session.session_id) is None

    def test_remove_nonexistent_session(self):
        """Test removing non-existent session doesn't error."""
        manager = SessionManager()
        manager.remove_session("nonexistent")  # Should not raise

    def test_session_touch(self):
        """Test updating session activity."""
        manager = SessionManager()
        mock_db = Mock()

        with patch('src.api.session.ChatInterface'):
            session = manager.create_session(mock_db, "localhost", 11434, "llama3.2")
            original_time = session.last_activity
            session.touch()

        assert session.last_activity >= original_time

    def test_cleanup_stale_sessions(self):
        """Test cleaning up stale sessions."""
        manager = SessionManager()
        mock_db = Mock()

        with patch('src.api.session.ChatInterface'):
            session = manager.create_session(mock_db, "localhost", 11434, "llama3.2")
            # Artificially age the session
            from datetime import datetime, timedelta
            session.last_activity = datetime.now() - timedelta(hours=2)

            removed = manager.cleanup_stale_sessions(max_age_minutes=60)

        assert removed == 1
        assert manager.active_sessions == 0


class TestWebSocketChat:
    """Tests for WebSocket chat endpoint."""

    def test_websocket_connect(self, client, mock_db, mock_config):
        """Test WebSocket connection."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                data = websocket.receive_json()

                assert data["type"] == "connected"
                assert data["payload"]["session_id"] == "test-session-id"
                assert "stats" in data["payload"]

    def test_websocket_ping_pong(self, client, mock_db, mock_config):
        """Test ping/pong messages."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send ping
                websocket.send_json({"type": "ping"})
                response = websocket.receive_json()

                assert response["type"] == "pong"

    def test_websocket_clear_context(self, client, mock_db, mock_config):
        """Test clearing chat context."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface.clear_context = Mock()
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send clear message
                websocket.send_json({"type": "clear"})
                response = websocket.receive_json()

                assert response["type"] == "cleared"
                mock_session.chat_interface.clear_context.assert_called_once()

    def test_websocket_chat_message(self, client, mock_db, mock_config):
        """Test sending a chat message."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []
            # ask() returns (response_text, transactions, llm_stats) tuple
            mock_session.chat_interface.ask.return_value = ("Test response", [], None)
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send chat message
                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Hello"}
                })
                response = websocket.receive_json()

                assert response["type"] == "chat_response"
                assert response["payload"]["message"] == "Test response"
                assert "timestamp" in response["payload"]

    def test_websocket_chat_message_with_llm_stats(self, client, mock_db, mock_config):
        """Test chat message response includes LLM stats when available."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []
            # Return LLM stats in the response
            llm_stats = {
                "completion_tokens": 50,
                "prompt_tokens": 100,
                "total_tokens": 150,
                "elapsed_time": 1.5,
                "tokens_per_second": 33.3,
            }
            mock_session.chat_interface.ask.return_value = ("Test response", [], llm_stats)
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send chat message
                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Hello"}
                })
                response = websocket.receive_json()

                assert response["type"] == "chat_response"
                assert response["payload"]["message"] == "Test response"
                assert "llm_stats" in response["payload"]
                assert response["payload"]["llm_stats"]["tokens_per_second"] == 33.3
                assert response["payload"]["llm_stats"]["elapsed_time"] == 1.5

    def test_websocket_empty_message(self, client, mock_db, mock_config):
        """Test sending empty message returns error."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send empty message
                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": ""}
                })
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["payload"]["code"] == "EMPTY_MESSAGE"

    def test_websocket_invalid_json(self, client, mock_db, mock_config):
        """Test sending invalid JSON returns error."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send invalid JSON
                websocket.send_text("not valid json")
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["payload"]["code"] == "INVALID_JSON"

    def test_websocket_unknown_type(self, client, mock_db, mock_config):
        """Test sending unknown message type."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send unknown type
                websocket.send_json({"type": "unknown"})
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["payload"]["code"] == "UNKNOWN_TYPE"

    def test_websocket_chat_error(self, client, mock_db, mock_config):
        """Test chat error handling."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []
            mock_session.chat_interface.ask.side_effect = Exception("Ollama error")
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                # Receive connected message
                websocket.receive_json()

                # Send chat message
                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Hello"}
                })
                response = websocket.receive_json()

                assert response["type"] == "error"
                assert response["payload"]["code"] == "CHAT_ERROR"
                assert "Ollama error" in response["payload"]["message"]

    def test_websocket_session_cleanup(self, client, mock_db, mock_config):
        """Test session is removed on disconnect."""
        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                websocket.receive_json()

            # After disconnect, session should be removed
            mock_manager.remove_session.assert_called_with("test-session-id")

    def test_websocket_cancel_during_chat(self, client, mock_db, mock_config):
        """Test cancelling an in-progress chat request."""
        import threading

        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []

            ask_release = threading.Event()

            def blocking_ask(query):
                ask_release.wait(timeout=5)
                return ("Response", [], None)

            mock_session.chat_interface.ask.side_effect = blocking_ask
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                websocket.receive_json()  # connected

                # Send chat (ask blocks in background thread)
                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Hello"}
                })
                # Send cancel while ask is still running
                websocket.send_json({"type": "cancel"})

                response = websocket.receive_json()
                assert response["type"] == "cancelled"

                ask_release.set()

    def test_websocket_ping_during_chat(self, client, mock_db, mock_config):
        """Test sending ping while chat is processing."""
        import threading

        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []

            ask_release = threading.Event()

            def blocking_ask(query):
                ask_release.wait(timeout=5)
                return ("Response", [], None)

            mock_session.chat_interface.ask.side_effect = blocking_ask
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                websocket.receive_json()  # connected

                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Hello"}
                })
                # Send ping while ask is blocking
                websocket.send_json({"type": "ping"})

                response = websocket.receive_json()
                assert response["type"] == "pong"

                # Let ask complete and verify the response still arrives
                ask_release.set()

                response = websocket.receive_json()
                assert response["type"] == "chat_response"
                assert response["payload"]["message"] == "Response"

    def test_websocket_cancel_cleanup_on_next_message(self, client, mock_db, mock_config):
        """Test cancelled task cleanup at start of next loop iteration."""
        import threading
        import time

        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []

            ask_release = threading.Event()

            def blocking_ask(query):
                ask_release.wait(timeout=5)
                # Simulate ask() appending to conversation history
                mock_session.chat_interface._conversation_history.extend([
                    {"role": "user", "content": "ctx"},
                    {"role": "assistant", "content": "resp"},
                ])
                return ("Response", [], None)

            mock_session.chat_interface.ask.side_effect = blocking_ask
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                websocket.receive_json()  # connected

                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Hello"}
                })
                websocket.send_json({"type": "cancel"})
                response = websocket.receive_json()
                assert response["type"] == "cancelled"

                # Release ask and let the thread finish
                ask_release.set()
                time.sleep(0.2)

                # Send ping to trigger next loop iteration;
                # pending_cancel_task.done() is True → cleanup at lines 71-76
                websocket.send_json({"type": "ping"})
                response = websocket.receive_json()
                assert response["type"] == "pong"

                # History should have been truncated back to pre-ask length (0)
                assert len(mock_session.chat_interface._conversation_history) == 0

    def test_websocket_cancel_cleanup_before_new_chat(self, client, mock_db, mock_config):
        """Test pending cancel task is awaited before processing a new chat."""
        import threading

        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []

            call_count = 0
            ask_release = threading.Event()

            def blocking_ask(query):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    ask_release.wait(timeout=5)
                    mock_session.chat_interface._conversation_history.extend([
                        {"role": "user", "content": "ctx1"},
                        {"role": "assistant", "content": "resp1"},
                    ])
                return ("Second response", [], None)

            mock_session.chat_interface.ask.side_effect = blocking_ask
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                websocket.receive_json()  # connected

                # First chat (blocks)
                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "First"}
                })
                websocket.send_json({"type": "cancel"})
                response = websocket.receive_json()
                assert response["type"] == "cancelled"

                # Send second chat while first task is still pending;
                # server hits lines 126-135 (await pending, truncate, reset)
                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Second"}
                })
                # Release first ask so the await in the handler completes
                ask_release.set()

                response = websocket.receive_json()
                assert response["type"] == "chat_response"
                assert response["payload"]["message"] == "Second response"

    def test_websocket_disconnect_with_pending_cancel(self, client, mock_db, mock_config):
        """Test session cleanup on disconnect with a pending cancelled task."""
        import threading

        with patch('src.api.routers.chat.session_manager') as mock_manager:
            mock_session = Mock()
            mock_session.session_id = "test-session-id"
            mock_session.chat_interface._conversation_history = []

            ask_release = threading.Event()

            def blocking_ask(query):
                ask_release.wait(timeout=5)
                return ("Response", [], None)

            mock_session.chat_interface.ask.side_effect = blocking_ask
            mock_manager.create_session.return_value = mock_session

            with client.websocket_connect("/ws/chat") as websocket:
                websocket.receive_json()  # connected

                websocket.send_json({
                    "type": "chat",
                    "payload": {"message": "Hello"}
                })
                websocket.send_json({"type": "cancel"})
                response = websocket.receive_json()
                assert response["type"] == "cancelled"

            # Disconnect happened with pending cancel task still running;
            # finally block (lines 243-246) cancels and awaits the task
            ask_release.set()  # Clean up the blocked thread
            mock_manager.remove_session.assert_called_with("test-session-id")


class TestLifespan:
    """Tests for application lifespan."""

    def test_lifespan_startup_shutdown(self):
        """Test lifespan context manager startup and shutdown."""
        import asyncio
        from fastapi import FastAPI

        # Create a minimal app for testing
        app = FastAPI()

        # Save real create_task before patching
        real_create_task = asyncio.create_task

        async def run_lifespan():
            # Track task operations
            task_created = False

            # Create a real task that we control
            async def dummy_task():
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    raise

            real_task = None

            def mock_create_task(coro):
                nonlocal task_created, real_task
                task_created = True
                # Close the passed coroutine to avoid warnings
                coro.close()
                # Create our own controlled task using real function
                real_task = real_create_task(dummy_task())
                return real_task

            # Patch at module level
            with patch('src.api.app.get_config') as mock_get_config, \
                 patch('src.api.app.Database') as mock_db_class, \
                 patch('src.api.app.asyncio.create_task', mock_create_task):
                mock_get_config.return_value = {
                    "paths": {"database": "test.db"},
                    "llm": {"host": "localhost", "port": 11434, "model": "llama3.2"},
                }
                mock_db = Mock()
                mock_db_class.return_value = mock_db

                # Import lifespan after patches are applied
                from src.api.app import lifespan

                # Use the lifespan context manager
                async with lifespan(app):
                    # Verify startup happened
                    assert hasattr(app.state, 'config')
                    assert hasattr(app.state, 'db')
                    mock_db_class.assert_called_with("test.db")
                    assert task_created

                # After exiting, cleanup task should have been cancelled
                assert real_task.cancelled() or real_task.done()

        asyncio.run(run_lifespan())

    def test_periodic_cleanup(self):
        """Test periodic cleanup function."""
        import asyncio
        from src.api.session import session_manager

        async def run_cleanup():
            call_count = 0

            async def mock_sleep_fn(seconds):
                nonlocal call_count
                call_count += 1
                if call_count > 1:
                    raise asyncio.CancelledError()

            # Patch session_manager's method directly
            with patch.object(session_manager, 'cleanup_stale_sessions') as mock_cleanup, \
                 patch('src.api.app.asyncio.sleep', mock_sleep_fn):

                from src.api.app import periodic_cleanup

                with pytest.raises(asyncio.CancelledError):
                    await periodic_cleanup()

                # cleanup_stale_sessions should have been called
                mock_cleanup.assert_called_with(max_age_minutes=60)

        asyncio.run(run_cleanup())


class TestAnalyticsEndpoints:
    """Tests for analytics endpoints."""

    def test_list_statements(self, client, mock_db, mock_config):
        """Test listing all statements."""
        mock_db.get_all_statements.return_value = [
            {"id": 1, "statement_number": "287", "statement_date": "2025-12-01", "account_number": "12345"},
            {"id": 2, "statement_number": "286", "statement_date": "2025-11-01", "account_number": "12345"},
        ]

        response = client.get("/api/v1/statements")

        assert response.status_code == 200
        data = response.json()
        assert len(data["statements"]) == 2
        assert data["statements"][0]["statement_number"] == "287"

    def test_get_latest_analytics(self, client, mock_db, mock_config):
        """Test getting analytics for latest statement."""
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": "287", "statement_date": "2025-12-01"
        }
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "groceries", "count": 10, "total_debits": 5000.00, "total_credits": 0.00},
            {"category": "fuel", "count": 5, "total_debits": 2000.00, "total_credits": 0.00},
        ]

        response = client.get("/api/v1/analytics/latest")

        assert response.status_code == 200
        data = response.json()
        assert data["statement_number"] == "287"
        assert data["total_debits"] == 7000.00
        assert data["transaction_count"] == 15
        assert len(data["categories"]) == 2

    def test_get_latest_analytics_no_statements(self, client, mock_db, mock_config):
        """Test getting analytics when no statements exist."""
        mock_db.get_latest_statement.return_value = None

        response = client.get("/api/v1/analytics/latest")

        assert response.status_code == 404
        assert "No statements found" in response.json()["detail"]

    def test_get_latest_analytics_no_statement_number(self, client, mock_db, mock_config):
        """Test getting analytics when latest statement has no statement number."""
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": None, "statement_date": "2025-12-01"
        }

        response = client.get("/api/v1/analytics/latest")

        assert response.status_code == 404
        assert "no statement number" in response.json()["detail"]

    def test_get_analytics_by_statement(self, client, mock_db, mock_config):
        """Test getting analytics for specific statement."""
        mock_db.get_all_statements.return_value = [
            {"id": 1, "statement_number": "287", "statement_date": "2025-12-01"}
        ]
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "groceries", "count": 10, "total_debits": 5000.00, "total_credits": 0.00},
        ]

        response = client.get("/api/v1/analytics/statement/287")

        assert response.status_code == 200
        data = response.json()
        assert data["statement_number"] == "287"

    def test_get_analytics_statement_not_found(self, client, mock_db, mock_config):
        """Test getting analytics for non-existent statement."""
        mock_db.get_all_statements.return_value = []

        response = client.get("/api/v1/analytics/statement/999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


class TestBudgetEndpoints:
    """Tests for budget management endpoints."""

    def test_list_budgets(self, client, mock_db, mock_config):
        """Test listing all budgets."""
        mock_db.get_all_budgets.return_value = [
            {"id": 1, "category": "groceries", "amount": 10000.00},
            {"id": 2, "category": "fuel", "amount": 5000.00},
        ]

        response = client.get("/api/v1/budgets")

        assert response.status_code == 200
        data = response.json()
        assert len(data["budgets"]) == 2

    def test_create_budget(self, client, mock_db, mock_config):
        """Test creating a budget."""
        mock_db.upsert_budget.return_value = 1
        mock_db.get_budget_by_category.return_value = {
            "id": 1, "category": "groceries", "amount": 10000.00
        }

        response = client.post(
            "/api/v1/budgets",
            json={"category": "groceries", "amount": 10000.00}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "groceries"
        assert data["amount"] == 10000.00

    def test_create_budget_negative_amount(self, client, mock_db, mock_config):
        """Test creating budget with negative amount fails."""
        response = client.post(
            "/api/v1/budgets",
            json={"category": "groceries", "amount": -100.00}
        )

        assert response.status_code == 400
        assert "positive" in response.json()["detail"]

    def test_create_budget_fetch_fails(self, client, mock_db, mock_config):
        """Test creating budget when fetch after insert fails."""
        mock_db.upsert_budget.return_value = 1
        mock_db.get_budget_by_category.return_value = None  # Simulate fetch failure

        response = client.post(
            "/api/v1/budgets",
            json={"category": "groceries", "amount": 10000.00}
        )

        assert response.status_code == 500
        assert "Failed to create budget" in response.json()["detail"]

    def test_delete_budget(self, client, mock_db, mock_config):
        """Test deleting a budget."""
        mock_db.delete_budget.return_value = True

        response = client.delete("/api/v1/budgets/groceries")

        assert response.status_code == 200
        assert response.json()["success"] is True

    def test_delete_budget_not_found(self, client, mock_db, mock_config):
        """Test deleting non-existent budget."""
        mock_db.delete_budget.return_value = False

        response = client.delete("/api/v1/budgets/nonexistent")

        assert response.status_code == 404

    def test_update_budget(self, client, mock_db, mock_config):
        """Test updating an existing budget."""
        mock_db.get_budget_by_category.side_effect = [
            {"id": 1, "category": "groceries", "amount": 5000.00},  # existing check
            {"id": 1, "category": "groceries", "amount": 7500.00},  # after update
        ]

        response = client.put(
            "/api/v1/budgets/groceries",
            json={"amount": 7500.00}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "groceries"
        assert data["amount"] == 7500.00
        mock_db.upsert_budget.assert_called_once_with("groceries", 7500.00)

    def test_update_budget_not_found(self, client, mock_db, mock_config):
        """Test updating a non-existent budget."""
        mock_db.get_budget_by_category.return_value = None

        response = client.put(
            "/api/v1/budgets/nonexistent",
            json={"amount": 5000.00}
        )

        assert response.status_code == 404
        assert "No budget found" in response.json()["detail"]

    def test_update_budget_negative_amount(self, client, mock_db, mock_config):
        """Test updating budget with negative amount."""
        mock_db.get_budget_by_category.return_value = {
            "id": 1, "category": "groceries", "amount": 5000.00
        }

        response = client.put(
            "/api/v1/budgets/groceries",
            json={"amount": -100.00}
        )

        assert response.status_code == 400
        assert "must be positive" in response.json()["detail"]

    def test_get_budget_summary(self, client, mock_db, mock_config):
        """Test getting budget summary with actuals."""
        mock_db.get_all_budgets.return_value = [
            {"id": 1, "category": "groceries", "amount": 10000.00},
            {"id": 2, "category": "fuel", "amount": 5000.00},
        ]
        mock_db.get_latest_statement.return_value = {
            "id": 1, "statement_number": "287"
        }
        mock_db.get_category_summary_for_statement.return_value = [
            {"category": "groceries", "count": 10, "total_debits": 8000.00, "total_credits": 0.00},
            {"category": "fuel", "count": 5, "total_debits": 6000.00, "total_credits": 0.00},
        ]

        response = client.get("/api/v1/budgets/summary")

        assert response.status_code == 200
        data = response.json()
        assert data["total_budgeted"] == 15000.00
        assert data["total_spent"] == 14000.00
        assert len(data["items"]) == 2
        # Fuel should be first (120% > 80%)
        assert data["items"][0]["category"] == "fuel"
        assert data["items"][0]["percentage"] == 120.0

    def test_get_budget_summary_no_statements(self, client, mock_db, mock_config):
        """Test budget summary when no statements exist."""
        mock_db.get_all_budgets.return_value = [
            {"id": 1, "category": "groceries", "amount": 10000.00},
        ]
        mock_db.get_latest_statement.return_value = None

        response = client.get("/api/v1/budgets/summary")

        assert response.status_code == 200
        data = response.json()
        # Should show 0 actual spending
        assert data["items"][0]["actual"] == 0
        assert data["items"][0]["percentage"] == 0

    def test_export_budgets(self, client, mock_db, mock_config):
        """Test exporting all budgets."""
        mock_db.get_all_budgets.return_value = [
            {"id": 1, "category": "groceries", "amount": 10000.00},
            {"id": 2, "category": "fuel", "amount": 5000.00},
        ]

        response = client.get("/api/v1/budgets/export")

        assert response.status_code == 200
        data = response.json()
        assert len(data["budgets"]) == 2
        assert data["budgets"][0]["category"] == "groceries"
        assert data["budgets"][0]["amount"] == 10000.00
        assert data["budgets"][1]["category"] == "fuel"
        assert data["budgets"][1]["amount"] == 5000.00

    def test_export_budgets_empty(self, client, mock_db, mock_config):
        """Test exporting when no budgets exist."""
        mock_db.get_all_budgets.return_value = []

        response = client.get("/api/v1/budgets/export")

        assert response.status_code == 200
        data = response.json()
        assert data["budgets"] == []

    def test_import_budgets(self, client, mock_db, mock_config):
        """Test importing budgets."""
        mock_db.delete_all_budgets.return_value = 2
        mock_db.upsert_budget.return_value = 1

        response = client.post(
            "/api/v1/budgets/import",
            json={
                "budgets": [
                    {"category": "groceries", "amount": 10000.00},
                    {"category": "fuel", "amount": 5000.00},
                ]
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["imported"] == 2
        assert data["deleted"] == 2
        assert mock_db.upsert_budget.call_count == 2

    def test_import_budgets_negative_amount(self, client, mock_db, mock_config):
        """Test importing budget with negative amount fails."""
        response = client.post(
            "/api/v1/budgets/import",
            json={
                "budgets": [
                    {"category": "groceries", "amount": -100.00},
                ]
            }
        )

        assert response.status_code == 400
        assert "positive" in response.json()["detail"]
        mock_db.delete_all_budgets.assert_not_called()

    def test_delete_all_budgets(self, client, mock_db, mock_config):
        """Test deleting all budgets."""
        mock_db.delete_all_budgets.return_value = 3

        response = client.delete("/api/v1/budgets")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["deleted"] == 3
