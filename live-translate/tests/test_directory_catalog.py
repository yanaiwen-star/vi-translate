from app.directory.catalog import (
    DOMAINS,
    DOMAIN_CODES,
    LANGUAGES,
    LANGUAGE_CODES,
    LANGUAGE_GROUPS,
    SERVICES,
)


def test_catalogs_are_complete_unique_and_ordered():
    assert len(LANGUAGES) == 59
    assert [row[0] for row in LANGUAGES[:3]] == ["vi", "zh", "en"]
    assert len(LANGUAGE_CODES) == len(LANGUAGES)
    assert len({row[2] for row in LANGUAGES}) == len(LANGUAGE_GROUPS)
    assert SERVICES == (("interpretation", "口译"), ("translation", "笔译"))
    assert len(DOMAINS) == 20
    assert len(DOMAIN_CODES) == len(DOMAINS)
    assert "general" in DOMAIN_CODES


def test_every_language_uses_a_known_group():
    group_codes = {code for code, _label in LANGUAGE_GROUPS}
    assert all(group in group_codes for _code, _label, group in LANGUAGES)
