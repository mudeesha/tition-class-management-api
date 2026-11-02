from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.models  # noqa: F401  (registers every model before the first query)
from app.core.config import settings
from app.core.exceptions import AppError
from app.modules.auth.router import router as auth_router
from app.modules.branches.router import halls_router
from app.modules.branches.router import router as branches_router
from app.modules.holidays.router import router as holidays_router
from app.modules.institute.router import router as institute_router
from app.modules.platform.router import router as platform_router
from app.modules.subjects.router import router as subjects_router
from app.modules.teachers.router import router as teachers_router
from app.modules.users.router import members_router, permissions_router, roles_router

API_PREFIX = "/api/v1"

app = FastAPI(
    title="Tuition Management API",
    version="0.1.0",
    description=(
        "Tenant endpoints need `Authorization: Bearer <token>` and "
        "`X-Tenant-ID: <institute id>` headers."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth_router,
    platform_router,
    institute_router,
    branches_router,
    halls_router,
    subjects_router,
    holidays_router,
    permissions_router,
    roles_router,
    members_router,
    teachers_router,
):
    app.include_router(router, prefix=API_PREFIX)


# Every error has the same shape: {"error": {"code", "message", "details"}}


def _error(status_code: int, code: str, message: str, details=None, headers=None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
        headers=headers,
    )


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return _error(exc.status_code, exc.code, exc.message, exc.details, headers)


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(
        422, "validation_error", "Some fields are invalid", jsonable_encoder(exc.errors())
    )


@app.exception_handler(StarletteHTTPException)
def handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "not_found" if exc.status_code == 404 else "http_error"
    return _error(exc.status_code, code, str(exc.detail), headers=exc.headers)


@app.exception_handler(IntegrityError)
def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
    # Services check the usual cases first; this catches races and records still in use.
    return _error(409, "conflict", "This record already exists or is still in use")


@app.get("/health", tags=["Health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
