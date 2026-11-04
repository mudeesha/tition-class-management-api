from app.tenancy.permissions import PERMISSION_CODES, PORTAL_CODES
from tests.helpers import PASSWORD, Api, error_code, login


def test_login_and_me(client, owner):
    res = owner.get("/auth/me")
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["email"] == "owner@saya.lk"
    assert [(m["tenant_code"], m["role"]["key"]) for m in body["memberships"]] == [
        ("saya", "owner")
    ]


def test_login_ignores_email_case(client, saya):
    login(client, "  OWNER@Saya.LK ")


def test_wrong_password_is_rejected(client, saya):
    res = client.post("/api/v1/auth/login", json={"login": "owner@saya.lk", "password": "nope"})
    assert res.status_code == 401
    assert error_code(res) == "unauthenticated"


def test_unknown_login_gets_same_error(client, saya):
    res = client.post("/api/v1/auth/login", json={"login": "ghost@saya.lk", "password": "nope"})
    assert res.status_code == 401
    assert res.json()["error"]["message"] == "Wrong login or password"


def test_refresh_gives_new_tokens(client, saya):
    tokens = client.post(
        "/api/v1/auth/login", json={"login": "owner@saya.lk", "password": PASSWORD}
    ).json()
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 200
    assert Api(client, res.json()["access_token"]).get("/auth/me").status_code == 200


def test_access_token_cannot_be_used_to_refresh(client, owner):
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": owner.token})
    assert res.status_code == 401


def test_requests_without_token_are_rejected(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
    assert res.headers["WWW-Authenticate"] == "Bearer"


def test_new_user_must_change_password_first(client, db, owner):
    roles = {r["key"]: r["id"] for r in owner.get("/roles").json()}
    owner.post(
        "/members",
        {
            "name": "Nimal",
            "email": "nimal@saya.lk",
            "password": PASSWORD,
            "role_id": roles["staff"],
        },
    )
    nimal = login(client, "nimal@saya.lk", tenant_id=owner.tenant_id)

    res = nimal.get("/auth/context")
    assert res.status_code == 403
    assert error_code(res) == "password_change_required"

    res = nimal.post(
        "/auth/change-password",
        {"current_password": PASSWORD, "new_password": "new-password-1"},
    )
    assert res.status_code == 200
    assert res.json()["must_change_password"] is False

    # The old token stops working; the new one works.
    assert nimal.get("/auth/me").status_code == 401
    renewed = Api(client, res.json()["access_token"], owner.tenant_id)
    assert renewed.get("/auth/context").status_code == 200


def test_change_password_checks_current_password(owner):
    res = owner.post(
        "/auth/change-password", {"current_password": "wrong-one", "new_password": "new-password-1"}
    )
    assert res.status_code == 422
    assert error_code(res) == "wrong_password"


def test_owner_context_has_every_permission(owner):
    body = owner.get("/auth/context").json()
    assert body["is_owner"] is True
    assert body["all_branches"] is True
    # Every staff permission; the portal ones are for a student's own records.
    assert set(body["permissions"]) == PERMISSION_CODES - PORTAL_CODES
    assert [b["code"] for b in body["branches"]] == ["MAIN"]


def test_tenant_header_is_required(owner):
    res = owner.in_tenant(None).get("/branches")
    assert res.status_code == 422
    assert error_code(res) == "tenant_required"
