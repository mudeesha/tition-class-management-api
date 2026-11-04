# Tuition Management API

FastAPI + SQLAlchemy 2 + Alembic + PostgreSQL.

## Run it

```bash
docker compose up -d                  # Postgres on localhost:5433 (+ a tuition_test database)
cp .env.example .env                  # then set JWT_SECRET
uv sync
uv run alembic upgrade head
uv run python -m app.cli setup        # permissions + default plans
uv run python -m app.cli create-admin --name "Your Name" --email you@example.com
uv run fastapi dev app/main.py        # http://localhost:8000/docs
```

Tests use the `tuition_test` database and roll back after each test:

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
```

## Calling the API

All endpoints are under `/api/v1`.

1. `POST /auth/login` with `{"login": "<email or username>", "password": "..."}`.
2. Send `Authorization: Bearer <access_token>` on every request.
3. `GET /auth/me` lists the institutes the user belongs to.
4. For institute endpoints, also send `X-Tenant-ID: <institute id>`.
   `GET /auth/context` returns the role, permissions and branches there; the UI builds its menu from it.

A new user must call `POST /auth/change-password` before anything else.
Errors always look like `{"error": {"code": "...", "message": "...", "details": ...}}`.

## Structure

```
app/
  core/        config, database, security (JWT, passwords), exceptions
  common/      base repositories, shared schemas (Page, Money, Percent, UpdateSchema)
  tenancy/     request context (user, institute, permissions, branches), permission list
  modules/     one folder per feature
    <module>/
      models.py        SQLAlchemy tables (entities)
      schemas.py       Pydantic request/response models (DTOs)
      repository.py    database queries
      service.py       business rules
      dependencies.py  Depends() wiring
      router.py        HTTP endpoints (controllers)
  models.py    imports every model (for Alembic)
  cli.py       setup commands
migrations/    Alembic
tests/
```

## Modules

| Module | What it covers |
| --- | --- |
| `platform` | Plans, institutes (tenants), usage and revenue for the platform admin |
| `auth` | Sign-in, refresh, password change, `/auth/me`, `/auth/context` |
| `users` | Roles, permissions, staff accounts (members), branch access |
| `institute` | Profile, fee settings, running numbers (student codes, receipt numbers) |
| `branches`, `subjects`, `holidays`, `teachers` | Setup |
| `classes` | Classes, weekly times with hall/teacher clash checks, timetable |
| `students` | Students, QR cards, portal logins, enrollments, half/free cards, promotion |
| `payments` | Dues, receipts, voids, cash handover; `fees.py` holds the fee rules |
| `attendance` | Class days (from the weekly times, skipping holidays), door scan, marking |
| `tutes` | Free/paid tutes, hard-copy ticks, PDF soft copies (access checked from payments) |
| `exams` | Exams with parts, marks, ranks (worked out, not stored) |
| `portal` | What a signed-in student sees about themselves |
| `settlements` | Teacher shares per month, payouts, balances |
| `reports` | Dashboard, fees owed, collections, attendance rates |

"Today" uses `TIMEZONE` (default Asia/Colombo) through `app/core/clock.py`; tests freeze it with
the `freeze` fixture. Uploaded files go to `STORAGE_DIR` through `app/core/storage.py`.

## Rules

- **Router**: no logic and no queries. Check permission with `dependencies=[requires("x.y")]`,
  call the service, and return. Use `response_model` for the output shape.
- **Service**: business rules and `db.commit()`. Never use `HTTPException` or `Request`. Raise
  `NotFound`, `Conflict`, `Forbidden`, `RuleViolation` or `PlanLimitReached` from `app.core.exceptions`.
- **Repository**: every SELECT lives here. Institute tables use `TenantScopedRepository`; tables
  with a required `branch_id` use `BranchScopedRepository`. Never build an institute-table query
  any other way, or one institute could see another's data.
- **Permissions**: add new codes to `app/tenancy/permissions.py`, then run
  `uv run python -m app.cli sync-permissions`.
- **Migrations**: after changing models, run
  `uv run alembic revision --autogenerate -m "what changed"`, read the file, then `uv run alembic upgrade head`.
- **New model**: import it in `app/models.py` so Alembic sees it.
