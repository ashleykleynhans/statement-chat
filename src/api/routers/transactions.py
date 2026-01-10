"""REST endpoints for transaction queries."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from ..models import TransactionListResponse, TransactionSchema

router = APIRouter()


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    request: Request,
    limit: int = Query(20, ge=1, le=100, description="Number of transactions to return"),
    offset: int = Query(0, ge=0, description="Number of transactions to skip"),
) -> TransactionListResponse:
    """Get paginated list of transactions, ordered by date descending."""
    db = request.app.state.db
    transactions = db.get_all_transactions(limit=limit, offset=offset)
    stats = db.get_stats()

    return TransactionListResponse(
        transactions=[TransactionSchema(**tx) for tx in transactions],
        total=stats["total_transactions"],
        limit=limit,
        offset=offset,
    )


@router.get("/transactions/search")
async def search_transactions(
    request: Request,
    q: str = Query(..., min_length=1, description="Search term"),
) -> dict:
    """Search transactions by description, recipient, or raw text."""
    db = request.app.state.db
    results = db.search_transactions(q)
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/category/{category}")
async def get_by_category(request: Request, category: str) -> dict:
    """Get all transactions for a specific category."""
    db = request.app.state.db
    results = db.get_transactions_by_category(category)
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/type/{tx_type}")
async def get_by_type(request: Request, tx_type: str) -> dict:
    """Get transactions by type (debit or credit)."""
    if tx_type not in ("debit", "credit"):
        raise HTTPException(
            status_code=400, detail="Type must be 'debit' or 'credit'"
        )
    db = request.app.state.db
    results = db.get_transactions_by_type(tx_type)
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/date-range")
async def get_by_date_range(
    request: Request,
    start: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end: date = Query(..., description="End date (YYYY-MM-DD)"),
) -> dict:
    """Get transactions within a date range."""
    if start > end:
        raise HTTPException(
            status_code=400, detail="Start date must be before or equal to end date"
        )
    db = request.app.state.db
    results = db.get_transactions_in_date_range(start.isoformat(), end.isoformat())
    return {"transactions": results, "count": len(results)}


@router.get("/transactions/statement/{statement_number}")
async def get_by_statement(request: Request, statement_number: str) -> dict:
    """Get all transactions for a specific statement."""
    db = request.app.state.db
    results = db.get_transactions_by_statement(statement_number)
    return {"transactions": results, "count": len(results)}
