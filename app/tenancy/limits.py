from app.core.exceptions import PlanLimitReached


def ensure_within_limit(limit: int | None, used: int, what: str) -> None:
    """Raise when adding one more `what` would go past the plan's limit (None = unlimited)."""
    if limit is not None and used >= limit:
        raise PlanLimitReached(
            f"Your plan allows up to {limit} {what}. Upgrade the plan to add more.",
            details={"limit": limit, "used": used},
        )
