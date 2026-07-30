from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from cryptography.fernet import Fernet

from app.directory.crypto import DirectoryCryptoError, decrypt_contacts, encrypt_contacts
from app.directory.moderation import (
    DirectoryValidationError,
    validate_code_list,
    validate_need_input,
    validate_profile_input,
)
from app.directory.catalog import LANGUAGE_CODES
from app.directory.service import cleanup_expired_directory_data, sort_profiles
from app.models import DirectoryNotification, TranslationNeed


def test_vietnamese_profiles_rank_first_and_order_is_stable():
    now = datetime.utcnow()
    profiles = [
        {"id": "b", "language_codes": ["en"], "completeness_score": 100, "last_active_at": now},
        {"id": "c", "language_codes": ["vi", "zh"], "completeness_score": 60, "last_active_at": now},
        {"id": "a", "language_codes": ["vi"], "completeness_score": 60, "last_active_at": now},
    ]
    rows = sort_profiles(profiles, now=now)
    assert [row["id"] for row in rows] == ["a", "c", "b"]


@pytest.mark.parametrize("note", ["加微信 abc123", "电话 13800138000", "a@b.com", "https://x.test"])
def test_need_note_rejects_contact_details(note):
    with pytest.raises(DirectoryValidationError):
        validate_need_input(
            {
                "source_lang": "zh",
                "target_lang": "vi",
                "service_type": "interpretation",
                "service_mode": "online",
                "note": note,
                "response_limit": 3,
            }
        )


def test_need_rejects_file_fields_and_profile_normalizes_nfc():
    with pytest.raises(DirectoryValidationError):
        validate_need_input(
            {
                "source_lang": "zh",
                "target_lang": "vi",
                "service_type": "translation",
                "service_mode": "online",
                "file": "contract.pdf",
            }
        )
    result = validate_profile_input(
        {
            "subject_type": "individual",
            "display_name": "Nguye\u0302\u0303n",
            "country_code": "VN",
            "city": "Ha\u0300 No\u0323\u0302i",
            "service_mode": "both",
            "languages": ["vi", "zh"],
            "services": ["interpretation"],
            "domains": ["business", "legal"],
            "bio": "Phiên dịch Việt Trung",
        }
    )
    assert result["display_name"] == "Nguyễn"
    assert result["city"] == "Hà Nội"


def test_contact_encryption_round_trip_and_wrong_key_fails():
    key = Fernet.generate_key().decode()
    ciphertext = encrypt_contacts({"wechat": "translator-vn"}, key=key)
    assert "translator-vn" not in ciphertext
    assert decrypt_contacts(ciphertext, key=key) == {"wechat": "translator-vn"}
    with pytest.raises(DirectoryCryptoError):
        decrypt_contacts(ciphertext, key=Fernet.generate_key().decode())


def test_validate_code_list_deduplicates_and_rejects_unknown_values():
    assert validate_code_list(
        ["vi", "vi", "zh"], LANGUAGE_CODES, "languages", 1, 12
    ) == ["vi", "zh"]
    with pytest.raises(DirectoryValidationError, match="languages"):
        validate_code_list(
            ["xx-invalid"], LANGUAGE_CODES, "languages", 1, 12
        )


def test_cleanup_deletes_expired_need_and_notification(db_session, test_user):
    now = datetime.utcnow()
    db_session.add_all(
        [
            TranslationNeed(
                requester_id=test_user.id,
                source_lang="zh",
                target_lang="vi",
                service_type="translation",
                service_mode="online",
                expires_at=now - timedelta(seconds=1),
            ),
            DirectoryNotification(
                user_id=test_user.id,
                kind="need_response",
                expires_at=now - timedelta(seconds=1),
            ),
        ]
    )
    db_session.commit()

    assert cleanup_expired_directory_data(db_session, now=now) == 2
    assert db_session.query(TranslationNeed).count() == 0
    assert db_session.query(DirectoryNotification).count() == 0
