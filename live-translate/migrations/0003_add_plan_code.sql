-- vi-translate: add stable `code` column to plans
-- Used by the pricing page (highlight labels / "推荐" ribbon) and by the
-- idempotent plan seeder for upsert matching. New column is nullable + unique
-- so existing rows (if any) stay valid; the seeder backfills `code`.

ALTER TABLE plans ADD COLUMN IF NOT EXISTS code VARCHAR(32) UNIQUE;
CREATE INDEX IF NOT EXISTS ix_plans_code ON plans (code);
