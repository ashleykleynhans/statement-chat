"""REST endpoints for analytics."""

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    AnalyticsResponse,
    CategorySummaryItem,
    StatementInfo,
    StatementListResponse,
)

router = APIRouter()


@router.get("/statements", response_model=StatementListResponse)
async def list_statements(request: Request) -> StatementListResponse:
    """Get list of all statements for dropdown selection."""
    db = request.app.state.db
    statements = db.get_all_statements()
    return StatementListResponse(
        statements=[StatementInfo(**s) for s in statements]
    )


@router.get("/analytics/latest", response_model=AnalyticsResponse)
async def get_latest_analytics(request: Request) -> AnalyticsResponse:
    """Get analytics for the most recent statement."""
    db = request.app.state.db
    latest = db.get_latest_statement()

    if not latest:
        raise HTTPException(status_code=404, detail="No statements found")

    statement_number = latest.get("statement_number")
    if not statement_number:
        raise HTTPException(status_code=404, detail="Latest statement has no statement number")

    return _get_analytics_for_statement(db, statement_number, latest.get("statement_date"))


@router.get("/analytics/statement/{statement_number}", response_model=AnalyticsResponse)
async def get_analytics_by_statement(
    request: Request,
    statement_number: str
) -> AnalyticsResponse:
    """Get analytics for a specific statement."""
    db = request.app.state.db

    # Get statement info
    statements = db.get_all_statements()
    statement = next(
        (s for s in statements if s.get("statement_number") == statement_number),
        None
    )

    if not statement:
        raise HTTPException(status_code=404, detail=f"Statement {statement_number} not found")

    return _get_analytics_for_statement(db, statement_number, statement.get("statement_date"))


def _get_analytics_for_statement(db, statement_number: str, statement_date: str | None) -> AnalyticsResponse:
    """Helper to build analytics response for a statement."""
    # Get category summary for this statement
    summary = db.get_category_summary_for_statement(statement_number)

    # Calculate totals
    total_debits = sum(abs(s.get("total_debits", 0) or 0) for s in summary)
    total_credits = sum(s.get("total_credits", 0) or 0 for s in summary)
    transaction_count = sum(s.get("count", 0) for s in summary)

    return AnalyticsResponse(
        statement_number=statement_number,
        statement_date=statement_date,
        total_debits=total_debits,
        total_credits=total_credits,
        transaction_count=transaction_count,
        categories=[CategorySummaryItem(**item) for item in summary]
    )
