from types import SimpleNamespace

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


@pytest.fixture
def campus(db, client) -> SimpleNamespace:
    """A multi-branch institute ready for classes: Galle and Kandy, halls, subjects, teachers.

    Sunil teaches in both branches, Amara only in Galle.
    """
    tenant = make_tenant(db, "chain", plan_code="multi_branch")
    owner = login(client, "owner@chain.lk", tenant_id=tenant.id)
    gal = owner.post("/branches", {"name": "Galle", "code": "GAL"}).json()
    kdy = owner.post("/branches", {"name": "Kandy", "code": "KDY"}).json()

    def make(url, body):
        res = owner.post(url, body)
        assert res.status_code == 201, res.text
        return res.json()

    return SimpleNamespace(
        tenant=tenant,
        owner=owner,
        gal=gal,
        kdy=kdy,
        hall_a=make("/halls", {"branch_id": gal["id"], "name": "Hall A"}),
        hall_b=make("/halls", {"branch_id": gal["id"], "name": "Hall B"}),
        kandy_hall=make("/halls", {"branch_id": kdy["id"], "name": "Main hall"}),
        maths=make("/subjects", {"name": "Mathematics", "level": "ol"}),
        physics=make("/subjects", {"name": "Physics", "level": "al"}),
        sunil=make("/teachers", {"name": "Sunil", "branch_ids": [gal["id"], kdy["id"]]}),
        amara=make("/teachers", {"name": "Amara", "branch_ids": [gal["id"]]}),
    )


@pytest.fixture
def freeze(monkeypatch):
    """`freeze(datetime(2027, 1, 10, 7, 45))` sets the app's clock (Sri Lanka time)."""
    import datetime as dt

    from app.core import clock

    def set_time(moment: dt.datetime) -> None:
        monkeypatch.setattr(clock, "now", lambda: moment.replace(tzinfo=clock._zone))

    return set_time


@pytest.fixture(autouse=True)
def storage_dir(tmp_path, monkeypatch):
    """Uploaded files go to a temporary folder."""
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
