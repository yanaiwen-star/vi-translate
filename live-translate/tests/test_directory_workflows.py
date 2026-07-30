from __future__ import annotations

from datetime import datetime, timedelta

from cryptography.fernet import Fernet
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from app.auth.jwt import require_user_id
from app.config import settings
from app.db import get_db
from app.main import app
from app.models import DirectoryNotification, User


def _current_user(x_test_user: str | None = Header(default=None)) -> str:
    if not x_test_user:
        raise HTTPException(status_code=401, detail="missing test identity")
    return x_test_user


def _client(db_session):
    def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[require_user_id] = _current_user
    return TestClient(app)


def _headers(user_id: str, key: str | None = None) -> dict[str, str]:
    value = {"X-Test-User": user_id}
    if key:
        value["Idempotency-Key"] = key
    return value


def _profile_payload(name="越南语译员", contacts=None):
    return {
        "subject_type": "individual",
        "display_name": name,
        "bio": "中越商务口译",
        "country_code": "VN",
        "city": "Hà Nội",
        "service_mode": "both",
        "languages": ["vi", "zh"],
        "services": ["interpretation", "translation"],
        "domains": ["business", "legal"],
        "contacts": contacts or {},
    }


def _need_payload(limit=3):
    return {
        "source_lang": "zh",
        "target_lang": "vi",
        "service_type": "interpretation",
        "service_mode": "online",
        "country_code": "VN",
        "city": "Hà Nội",
        "note": "下周商务会议需要口译",
        "response_limit": limit,
    }


def _new_user(db_session, email):
    user = User(email=email, password_hash="x")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_duplicate_contact_request_is_idempotent(db_session, test_user):
    requester = _new_user(db_session, "requester@example.test")
    old_key = settings.directory_contact_key
    settings.directory_contact_key = Fernet.generate_key().decode()
    try:
        with _client(db_session) as client:
            profile = client.post(
                "/api/directory/me/profile",
                json=_profile_payload(contacts={"wechat": "translator-vn"}),
                headers=_headers(test_user.id),
            ).json()
            first = client.post(
                f"/api/directory/profiles/{profile['id']}/contact-requests",
                json={"purpose": "咨询商务口译档期"},
                headers=_headers(requester.id, "same-request"),
            )
            second = client.post(
                f"/api/directory/profiles/{profile['id']}/contact-requests",
                json={"purpose": "咨询商务口译档期"},
                headers=_headers(requester.id, "same-request"),
            )
            assert first.status_code == 201
            assert second.status_code == 200
            assert first.json()["id"] == second.json()["id"]
            assert db_session.query(DirectoryNotification).count() == 1
    finally:
        settings.directory_contact_key = old_key


def test_approved_contact_stops_after_profile_pause(db_session, test_user):
    requester = _new_user(db_session, "contact-reader@example.test")
    old_key = settings.directory_contact_key
    settings.directory_contact_key = Fernet.generate_key().decode()
    try:
        with _client(db_session) as client:
            profile = client.post(
                "/api/directory/me/profile",
                json=_profile_payload(contacts={"wechat": "translator-vn"}),
                headers=_headers(test_user.id),
            ).json()
            request_id = client.post(
                f"/api/directory/profiles/{profile['id']}/contact-requests",
                json={"purpose": "希望了解服务时间"},
                headers=_headers(requester.id, "grant-request"),
            ).json()["id"]
            approved = client.post(
                f"/api/directory/me/contact-requests/{request_id}/approve",
                headers=_headers(test_user.id),
            )
            assert approved.status_code == 200
            granted = client.get(
                f"/api/directory/me/contact-grants/{request_id}",
                headers=_headers(requester.id),
            )
            assert granted.json()["contacts"] == {"wechat": "translator-vn"}
            client.post("/api/directory/me/profile/pause", headers=_headers(test_user.id))
            expired = client.get(
                f"/api/directory/me/contact-grants/{request_id}",
                headers=_headers(requester.id),
            )
            assert expired.status_code == 410
    finally:
        settings.directory_contact_key = old_key


def test_example_and_self_contact_requests_are_rejected(db_session, test_user):
    with _client(db_session) as client:
        example = client.post(
            "/api/directory/profiles/example:vi-cn-interpreter/contact-requests",
            json={"purpose": "联系"},
            headers=_headers(test_user.id),
        )
        assert example.status_code == 400
        profile = client.post(
            "/api/directory/me/profile",
            json=_profile_payload(),
            headers=_headers(test_user.id),
        ).json()
        own = client.post(
            f"/api/directory/profiles/{profile['id']}/contact-requests",
            json={"purpose": "联系"},
            headers=_headers(test_user.id),
        )
        assert own.status_code == 400


def test_contact_request_can_be_resubmitted_after_rejection_without_idempotency_key(
    db_session, test_user
):
    requester = _new_user(db_session, "contact-reapply@example.test")
    with _client(db_session) as client:
        profile = client.post(
            "/api/directory/me/profile",
            json=_profile_payload(),
            headers=_headers(test_user.id),
        ).json()
        first = client.post(
            f"/api/directory/profiles/{profile['id']}/contact-requests",
            json={"purpose": "希望了解服务时间"},
            headers=_headers(requester.id),
        )
        assert first.status_code == 201
        rejected = client.post(
            f"/api/directory/me/contact-requests/{first.json()['id']}/reject",
            headers=_headers(test_user.id),
        )
        assert rejected.status_code == 200

        second = client.post(
            f"/api/directory/profiles/{profile['id']}/contact-requests",
            json={"purpose": "再次申请联系方式"},
            headers=_headers(requester.id),
        )

        assert second.status_code == 201
        assert second.json()["id"] != first.json()["id"]
        assert second.json()["status"] == "pending"


def test_need_is_private_matched_and_expires_in_seven_days(db_session, test_user):
    translator = _new_user(db_session, "matched@example.test")
    with _client(db_session) as client:
        client.post(
            "/api/directory/me/profile",
            json=_profile_payload(),
            headers=_headers(translator.id),
        )
        created = client.post(
            "/api/directory/needs", json=_need_payload(), headers=_headers(test_user.id)
        )
        assert created.status_code == 201
        expires = datetime.fromisoformat(created.json()["expires_at"])
        assert timedelta(days=6, hours=23) < expires - datetime.utcnow() <= timedelta(days=7)
        matched = client.get(
            "/api/directory/me/matched-needs", headers=_headers(translator.id)
        )
        assert [item["id"] for item in matched.json()["items"]] == [created.json()["id"]]


def test_need_response_is_idempotent_and_respects_limit(db_session, test_user):
    translator_one = _new_user(db_session, "translator1@example.test")
    translator_two = _new_user(db_session, "translator2@example.test")
    with _client(db_session) as client:
        for user, name in ((translator_one, "译员一"), (translator_two, "译员二")):
            client.post(
                "/api/directory/me/profile",
                json=_profile_payload(name=name),
                headers=_headers(user.id),
            )
        need = client.post(
            "/api/directory/needs", json=_need_payload(limit=1), headers=_headers(test_user.id)
        ).json()
        first = client.post(
            f"/api/directory/needs/{need['id']}/respond",
            headers=_headers(translator_one.id, "respond-once"),
        )
        duplicate = client.post(
            f"/api/directory/needs/{need['id']}/respond",
            headers=_headers(translator_one.id, "respond-once"),
        )
        full = client.post(
            f"/api/directory/needs/{need['id']}/respond",
            headers=_headers(translator_two.id, "respond-two"),
        )
        assert first.status_code == 201
        assert duplicate.status_code == 200
        assert full.status_code == 409


def test_notifications_are_fixed_templates_without_free_chat(db_session, test_user):
    with _client(db_session) as client:
        response = client.get(
            "/api/directory/notifications", headers=_headers(test_user.id)
        )
        assert response.status_code == 200
        assert response.json()["free_chat_enabled"] is False
        assert "body" not in {column.name for column in DirectoryNotification.__table__.columns}


def teardown_module():
    app.dependency_overrides.clear()
