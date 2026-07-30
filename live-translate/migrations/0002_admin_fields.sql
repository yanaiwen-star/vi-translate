-- vi-translate v2: admin / ban / phone / wechat_openid
-- Adds the columns required by the admin console (role, ban flag) and the
-- future SMS / WeChat login paths. Safe to run repeatedly.
--
-- Run with: psql "$DATABASE_URL" -f migrations/0002_admin_fields.sql

-- Idempotent ALTERs for SQLite + PostgreSQL.
-- Each statement uses ADD COLUMN IF NOT EXISTS where the engine supports it,
-- and a guarded DO block for engines (older SQLite) that don't.
-- For SQLite <3.35 we recommend: re-creating the users table; the manual is
-- included below as a comment for reference.
--
-- BEGIN SQLite manual migration (only if IF NOT EXISTS is unavailable):
--   ALTER TABLE users ADD COLUMN role           VARCHAR(16) NOT NULL DEFAULT 'user';
--   ALTER TABLE users ADD COLUMN is_banned       BOOLEAN     NOT NULL DEFAULT 0;
--   ALTER TABLE users ADD COLUMN phone           VARCHAR(32);
--   ALTER TABLE users ADD COLUMN wechat_openid   VARCHAR(64);
--   CREATE INDEX IF NOT EXISTS ix_users_role          ON users (role);
--   CREATE INDEX IF NOT EXISTS ix_users_is_banned     ON users (is_banned);
--   CREATE INDEX IF NOT EXISTS ix_users_phone         ON users (phone);
--   CREATE INDEX IF NOT EXISTS ix_users_wechat_openid ON users (wechat_openid);

-- PostgreSQL / MySQL flavour (IF NOT EXISTS):
ALTER TABLE users ADD COLUMN IF NOT EXISTS role           VARCHAR(16) NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned       BOOLEAN     NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone           VARCHAR(32);
ALTER TABLE users ADD COLUMN IF NOT EXISTS wechat_openid   VARCHAR(64);

CREATE INDEX IF NOT EXISTS ix_users_role          ON users (role);
CREATE INDEX IF NOT EXISTS ix_users_is_banned     ON users (is_banned);
CREATE INDEX IF NOT EXISTS ix_users_phone         ON users (phone);
CREATE INDEX IF NOT EXISTS ix_users_wechat_openid ON users (wechat_openid);

-- Verification query (run after migration):
--   SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'users'
--     AND column_name IN ('role','is_banned','phone','wechat_openid');
