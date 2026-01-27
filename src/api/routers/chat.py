"""WebSocket endpoint for real-time chat."""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..session import session_manager

router = APIRouter()


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket endpoint for chat conversations.

    Each connection gets its own ChatInterface with separate conversation history.

    Message Protocol:
        Client -> Server:
            {"type": "chat", "payload": {"message": "..."}}
            {"type": "cancel"}
            {"type": "ping"}

        Server -> Client:
            {"type": "connected", "payload": {"session_id": "...", "stats": {...}}}
            {"type": "chat_response", "payload": {"message": "...", "transactions": [...], "timestamp": "..."}}
            {"type": "cancelled"}
            {"type": "error", "payload": {"code": "...", "message": "..."}}
            {"type": "pong"}
    """
    await websocket.accept()

    # Get shared resources from app state
    app = websocket.app
    config = app.state.config
    db = app.state.db

    # Create session for this connection
    session = session_manager.create_session(
        db=db,
        host=config["llm"]["host"],
        port=config["llm"]["port"],
        model=config["llm"]["model"],
    )

    # Track a cancelled-but-still-running LLM task so we can clean up
    # its conversation history changes once the thread finishes.
    pending_cancel_task = None
    pending_cancel_history_len = 0

    try:
        # Send connection acknowledgment with stats
        stats = db.get_stats()
        await websocket.send_json(
            {
                "type": "connected",
                "payload": {
                    "session_id": session.session_id,
                    "stats": stats,
                },
            }
        )

        # Message loop
        while True:
            # Non-blocking cleanup: if a previously cancelled LLM thread
            # has finished, roll back its conversation history changes.
            if pending_cancel_task is not None and pending_cancel_task.done():
                session.chat_interface._conversation_history[:] = (
                    session.chat_interface._conversation_history[
                        :pending_cancel_history_len
                    ]
                )
                pending_cancel_task = None

            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "payload": {
                            "code": "INVALID_JSON",
                            "message": "Invalid JSON message",
                        },
                    }
                )
                continue

            msg_type = message.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if msg_type == "clear":
                session.chat_interface.clear_context()
                await websocket.send_json({"type": "cleared"})
                continue

            if msg_type == "chat":
                payload = message.get("payload", {})
                query = payload.get("message", "").strip()

                if not query:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "payload": {
                                "code": "EMPTY_MESSAGE",
                                "message": "Message cannot be empty",
                            },
                        }
                    )
                    continue

                session.touch()

                # If a previous cancelled LLM thread is still running,
                # wait for it to finish so we can safely reset history.
                if pending_cancel_task is not None:
                    try:
                        await pending_cancel_task
                    except Exception:
                        pass
                    session.chat_interface._conversation_history[:] = (
                        session.chat_interface._conversation_history[
                            :pending_cancel_history_len
                        ]
                    )
                    pending_cancel_task = None

                # Snapshot history length so we can roll back on cancel.
                history_len = len(
                    session.chat_interface._conversation_history
                )

                # Run the blocking LLM call in a background thread so the
                # WebSocket stays responsive to cancel / ping messages.
                ask_task = asyncio.ensure_future(
                    asyncio.to_thread(session.chat_interface.ask, query)
                )

                cancelled = False

                while not ask_task.done():
                    recv_task = asyncio.ensure_future(
                        websocket.receive_text()
                    )
                    done, _pending = await asyncio.wait(
                        {ask_task, recv_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    # If the LLM finished first, cancel the pending receive
                    # and break out so we can send the response.
                    if recv_task not in done:
                        recv_task.cancel()
                        try:
                            await recv_task
                        except asyncio.CancelledError:
                            pass
                        break

                    # A WebSocket message arrived — handle it.
                    try:
                        inner_raw = recv_task.result()
                        inner_data = json.loads(inner_raw)
                    except WebSocketDisconnect:
                        raise
                    except Exception:
                        continue

                    inner_type = inner_data.get("type")

                    if inner_type == "cancel":
                        cancelled = True
                        await websocket.send_json({"type": "cancelled"})
                        # The thread is still running; stash it for cleanup.
                        pending_cancel_task = ask_task
                        pending_cancel_history_len = history_len
                        break
                    elif inner_type == "ping":
                        await websocket.send_json({"type": "pong"})
                    # Any other message type is ignored while waiting.

                if cancelled:
                    continue

                try:
                    response_text, transactions, llm_stats = (
                        ask_task.result()
                    )

                    # Limit to 20 transactions, frontend filters out fees
                    transactions = transactions[:20]

                    resp_payload = {
                        "message": response_text,
                        "transactions": transactions,
                        "timestamp": datetime.now().isoformat(),
                    }

                    # Include LLM stats if available
                    if llm_stats:
                        resp_payload["llm_stats"] = llm_stats

                    await websocket.send_json(
                        {
                            "type": "chat_response",
                            "payload": resp_payload,
                        }
                    )
                except Exception as e:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "payload": {
                                "code": "CHAT_ERROR",
                                "message": str(e),
                            },
                        }
                    )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "payload": {
                            "code": "UNKNOWN_TYPE",
                            "message": f"Unknown message type: {msg_type}",
                        },
                    }
                )

    except WebSocketDisconnect:
        pass
    finally:
        if pending_cancel_task is not None and not pending_cancel_task.done():
            pending_cancel_task.cancel()
            try:
                await pending_cancel_task
            except (asyncio.CancelledError, Exception):
                pass
        session_manager.remove_session(session.session_id)
