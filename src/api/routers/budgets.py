"""REST endpoints for budget management."""

from fastapi import APIRouter, HTTPException, Request

from ..models import (
    BudgetCreate,
    BudgetListResponse,
    BudgetResponse,
    BudgetSummaryItem,
    BudgetSummaryResponse,
)

router = APIRouter()


@router.get("/budgets", response_model=BudgetListResponse)
async def list_budgets(request: Request) -> BudgetListResponse:
    """Get all budget entries."""
    db = request.app.state.db
    budgets = db.get_all_budgets()
    return BudgetListResponse(
        budgets=[BudgetResponse(**b) for b in budgets]
    )


@router.post("/budgets", response_model=BudgetResponse)
async def create_or_update_budget(
    request: Request,
    budget: BudgetCreate
) -> BudgetResponse:
    """Create or update a budget for a category."""
    db = request.app.state.db

    if budget.amount < 0:
        raise HTTPException(status_code=400, detail="Budget amount must be positive")

    db.upsert_budget(budget.category, budget.amount)

    # Fetch the updated budget to return
    updated = db.get_budget_by_category(budget.category)
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to create budget")

    return BudgetResponse(**updated)


@router.delete("/budgets/{category}")
async def delete_budget(request: Request, category: str) -> dict:
    """Delete a budget by category."""
    db = request.app.state.db

    deleted = db.delete_budget(category)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No budget found for category: {category}")

    return {"success": True, "category": category}


@router.get("/budgets/summary", response_model=BudgetSummaryResponse)
async def get_budget_summary(request: Request) -> BudgetSummaryResponse:
    """Get budget summary with actual spending comparison for the latest statement."""
    db = request.app.state.db

    # Get all budgets
    budgets = db.get_all_budgets()

    # Get latest statement
    latest = db.get_latest_statement()
    statement_number = latest.get("statement_number") if latest else None

    # Get actual spending by category for the latest statement
    actual_spending = {}
    if statement_number:
        summary = db.get_category_summary_for_statement(statement_number)
        for item in summary:
            category = item.get("category")
            if category:
                actual_spending[category] = abs(item.get("total_debits", 0) or 0)

    # Build summary items
    items = []
    total_budgeted = 0
    total_spent = 0

    for budget in budgets:
        category = budget["category"]
        budget_amount = budget["amount"]
        actual = actual_spending.get(category, 0)
        remaining = budget_amount - actual
        percentage = (actual / budget_amount * 100) if budget_amount > 0 else 0

        items.append(BudgetSummaryItem(
            category=category,
            budget=budget_amount,
            actual=actual,
            remaining=remaining,
            percentage=round(percentage, 1)
        ))

        total_budgeted += budget_amount
        total_spent += actual

    # Sort by percentage descending (most over-budget first)
    items.sort(key=lambda x: x.percentage, reverse=True)

    return BudgetSummaryResponse(
        items=items,
        total_budgeted=total_budgeted,
        total_spent=total_spent
    )
