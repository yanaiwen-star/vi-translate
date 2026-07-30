-- vi-translate: add customer display name (nickname) to users
-- The mini program lets a customer set a custom name, or adopt their WeChat
-- nickname (captured client-side via <input type="nickname">). Nullable so
-- existing rows keep working; the profile page falls back to a default label.

ALTER TABLE users ADD COLUMN IF NOT EXISTS nickname VARCHAR(64);
CREATE INDEX IF NOT EXISTS ix_users_nickname ON users (nickname);
