from __future__ import annotations

from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from app.auth.jwt import require_user_id
from app.db import get_db
from app.main import app
from app.models import User


def _current_user(x_test_user: str | None = Header(default=None)) -> str:
    if not x_test_user:
        raise HTTPException(status_code=401, detail="missing test identity")
    return x_test_user


def _profile_payload(**changes):
    payload = {
        "subject_type": "individual",
        "display_name": "阮氏越中翻译",
        "bio": "提供中越商务口译服务",
        "country_code": "VN",
        "city": "Hà Nội",
        "service_mode": "both",
        "languages": ["vi", "zh"],
        "services": ["interpretation", "translation"],
        "domains": ["business", "legal"],
        "contacts": {},
    }
    payload.update(changes)
    return payload


def _client(db_session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_user_id] = _current_user
    return TestClient(app)


def test_public_directory_lists_clearly_labeled_examples(db_session):
    with _client(db_session) as client:
        response = client.get("/api/directory/profiles")
        assert response.status_code == 200
        rows = response.json()["items"]
        assert rows
        assert rows[0]["language_codes"][0] == "vi"
        assert all(row["is_example"] for row in rows)
        assert all(row["example_label"] == "示例资料·招募中" for row in rows)
        assert all(row["contact_request_allowed"] is False for row in rows)


def test_options_expose_grouped_languages_two_services_and_domains(db_session):
    with _client(db_session) as client:
        response = client.get("/api/directory/options")
        assert response.status_code == 200
        body = response.json()
        assert len(body["languages"]) == 59
        assert [item["code"] for item in body["languages"][:3]] == ["vi", "zh", "en"]
        assert [item["code"] for item in body["services"]] == [
            "interpretation", "translation"
        ]
        assert len(body["domains"]) == 20
        assert body["language_groups"][0]["code"] == "priority"


def test_profile_write_requires_login(db_session):
    with _client(db_session) as client:
        response = client.post("/api/directory/me/profile", json=_profile_payload())
        assert response.status_code in (401, 403)


def test_owner_creates_profile_without_leaking_contacts(db_session, test_user):
    headers = {"X-Test-User": test_user.id}
    with _client(db_session) as client:
        created = client.post(
            "/api/directory/me/profile", json=_profile_payload(), headers=headers
        )
        assert created.status_code == 201
        profile_id = created.json()["id"]
        public = client.get(f"/api/directory/profiles/{profile_id}")
        assert public.status_code == 200
        serialized = str(public.json())
        assert "contact_ciphertext" not in serialized
        assert "contacts" not in public.json()
        assert public.json()["verification_status"] == "unverified"
        assert public.json()["service_codes"] == ["interpretation", "translation"]
        assert public.json()["domain_codes"] == ["business", "legal"]


def test_profile_round_trip_and_domain_filter(db_session, test_user):
    headers = {"X-Test-User": test_user.id}
    with _client(db_session) as client:
        created = client.post(
            "/api/directory/me/profile", json=_profile_payload(), headers=headers
        )
        assert created.status_code == 201
        assert created.json()["domain_codes"] == ["business", "legal"]

        rows = client.get("/api/directory/profiles?domain=legal").json()["items"]
        real_rows = [row for row in rows if not row["is_example"]]
        assert [row["id"] for row in real_rows] == [created.json()["id"]]

        excluded = client.get("/api/directory/profiles?domain=medical").json()["items"]
        assert created.json()["id"] not in [row["id"] for row in excluded]


def test_missing_own_profile_is_an_empty_state_not_an_http_error(db_session, test_user):
    with _client(db_session) as client:
        response = client.get(
            "/api/directory/me/profile",
            headers={"X-Test-User": test_user.id},
        )

        assert response.status_code == 200
        assert response.json() == {"exists": False}


def test_other_user_cannot_update_profile(db_session, test_user):
    other = User(email="other@example.test", password_hash="x")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    with _client(db_session) as client:
        created = client.post(
            "/api/directory/me/profile",
            json=_profile_payload(),
            headers={"X-Test-User": test_user.id},
        )
        assert created.status_code == 201
        response = client.put(
            "/api/directory/me/profile",
            json=_profile_payload(display_name="冒名修改"),
            headers={"X-Test-User": other.id},
        )
        assert response.status_code == 404


def test_profile_schema_rejects_unknown_fields(db_session, test_user):
    with _client(db_session) as client:
        response = client.post(
            "/api/directory/me/profile",
            json=_profile_payload(is_recommended=True),
            headers={"X-Test-User": test_user.id},
        )
        assert response.status_code == 422


def teardown_module():
    app.dependency_overrides.clear()
