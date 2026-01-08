"""FastAPI application for statement-chat API."""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..config import get_config
from ..database import Database
from .routers import analytics, budgets, chat, stats, transactions
from .session import session_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan - startup and shutdown tasks."""
    # Startup: Load config and create shared database connection
    config = get_config()
    app.state.config = config
    app.state.db = Database(config["paths"]["database"])

    # Start background task for session cleanup
    cleanup_task = asyncio.create_task(periodic_cleanup())

    yield

    # Shutdown: Cancel cleanup task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


async def periodic_cleanup() -> None:
    """Periodically clean up stale sessions."""
    while True:
        await asyncio.sleep(300)  # Every 5 minutes
        session_manager.cleanup_stale_sessions(max_age_minutes=60)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="BankBot API",
        description="API for querying bank statements with a local AI",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS configuration for browser clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(chat.router, prefix="/ws", tags=["chat"])
    app.include_router(stats.router, prefix="/api/v1", tags=["stats"])
    app.include_router(transactions.router, prefix="/api/v1", tags=["transactions"])
    app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])
    app.include_router(budgets.router, prefix="/api/v1", tags=["budgets"])

    @app.get("/health", tags=["health"])
    async def health_check() -> dict:
        """Health check endpoint."""
        return {
            "status": "healthy",
            "active_sessions": session_manager.active_sessions,
        }

    return app


# Create app instance
app = create_app()
