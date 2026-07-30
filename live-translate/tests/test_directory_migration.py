from pathlib import Path


def test_migration_is_transactional_and_preserves_legacy_need_column():
    sql = Path("migrations/0004_directory_classification.sql").read_text("utf-8")
    assert sql.startswith("BEGIN;")
    assert sql.rstrip().endswith("COMMIT;")
    assert "DROP COLUMN service_type" not in sql
    assert "profile_domains" in sql
    assert "need_services" in sql
    assert "need_domains" in sql
    assert "simultaneous" in sql
    assert "escort" in sql
    assert "technical" in sql


def test_migration_backfills_stable_relations_before_cleanup():
    sql = Path("migrations/0004_directory_classification.sql").read_text("utf-8")
    assert "md5(" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert sql.index("INSERT INTO profile_domains") < sql.index("DELETE FROM profile_services")
    assert "general" in sql
    assert "interpretation" in sql
    assert "translation" in sql
