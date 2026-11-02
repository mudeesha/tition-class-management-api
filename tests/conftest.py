import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401
from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.platform.service import seed_default_plans
from app.modules.users.models import User
from app.modules.users.service import sync_permissions
from tests.helpers import PASSWORD, Api, login, make_tenant


@pytest.fixture(scope="session")
def engine():
    if not settings.test_database_url:
        pytest.exit("Set TEST_DATABASE_URL in .env")
    engine = create_engine(settings.test_database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        sync_permissions(db)
        seed_default_plans(db)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    """A session whose commits are rolled back after each test."""
    with engine.connect() as conn:
        outer = conn.begin()
        session = Session(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def saya(db):
    """A single-branch institute."""
    return make_tenant(db, "saya")


@pytest.fixture
def owner(client, saya) -> Api:
    return login(client, "owner@saya.lk", tenant_id=saya.id)


@pytest.fixture
def admin(client, db) -> Api:
    db.add(
        User(
            name="Platform admin",
            email="admin@platform.lk",
            password_hash=hash_password(PASSWORD),
            is_platform_admin=True,
        )
    )
    db.commit()
    return login(client, "admin@platform.lk")
