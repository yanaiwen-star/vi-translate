from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    NeedDomain,
    NeedResponse,
    NeedService,
    ProfileDomain,
    ProfileLanguage,
    TranslationNeed,
    TranslatorProfile,
)


def _profile(user_id: str, name: str = "越南语口译") -> TranslatorProfile:
    return TranslatorProfile(
        user_id=user_id,
        subject_type="individual",
        display_name=name,
        country_code="CN",
        city="南宁",
        service_mode="both",
    )


def test_only_one_translator_profile_per_user(db_session, test_user):
    db_session.add(_profile(test_user.id))
    db_session.commit()

    db_session.add(_profile(test_user.id, "第二张资料"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_profile_language_is_unique(db_session, test_user):
    profile = _profile(test_user.id)
    db_session.add(profile)
    db_session.flush()
    db_session.add_all(
        [
            ProfileLanguage(profile_id=profile.id, language_code="vi"),
            ProfileLanguage(profile_id=profile.id, language_code="vi"),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_need_response_is_unique_per_profile(db_session, test_user):
    profile = _profile(test_user.id)
    db_session.add(profile)
    db_session.flush()
    need = TranslationNeed(
        requester_id=test_user.id,
        source_lang="zh",
        target_lang="vi",
        service_type="interpretation",
        service_mode="online",
        response_limit=3,
    )
    db_session.add(need)
    db_session.flush()
    db_session.add_all(
        [
            NeedResponse(need_id=need.id, profile_id=profile.id),
            NeedResponse(need_id=need.id, profile_id=profile.id),
        ]
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_profile_has_no_plaintext_contact_column():
    names = {column.name for column in TranslatorProfile.__table__.columns}
    assert "contact_ciphertext" in names
    assert not {"phone", "wechat", "email"} & names


def test_new_classification_relations_have_unique_pairs():
    assert {column.name for column in ProfileDomain.__table__.columns} == {
        "id", "profile_id", "domain_code"
    }
    assert {column.name for column in NeedService.__table__.columns} == {
        "id", "need_id", "service_code"
    }
    assert {column.name for column in NeedDomain.__table__.columns} == {
        "id", "need_id", "domain_code"
    }

    for model in (ProfileDomain, NeedService, NeedDomain):
        constraints = [
            constraint
            for constraint in model.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]
        assert len(constraints) == 1
