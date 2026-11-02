"""Business errors raised by services. main.py turns them into HTTP responses.

Services never raise HTTPException, so they stay usable outside a request
(CLI commands, background jobs, tests).
"""

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Bad request"

    def __init__(
        self, message: str | None = None, *, code: str | None = None, details: Any = None
    ) -> None:
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        super().__init__(self.message)


class AuthenticationFailed(AppError):
    status_code = 401
    code = "unauthenticated"
    message = "Sign in required"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"
    message = "You don't have access to this"


class PlanLimitReached(AppError):
    status_code = 403
    code = "plan_limit_reached"
    message = "Your plan limit has been reached"


class NotFound(AppError):
    status_code = 404
    code = "not_found"
    message = "Not found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"
    message = "This conflicts with existing data"


class RuleViolation(AppError):
    status_code = 422
    code = "rule_violation"
    message = "This action is not allowed"
