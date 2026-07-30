-- vi-translate initial schema
-- Run with: psql "$DATABASE_URL" -f migrations/0001_init.sql

CREATE TABLE IF NOT EXISTS users (
    id               VARCHAR(36) PRIMARY KEY,
    email            VARCHAR(255) UNIQUE NOT NULL,
    password_hash    VARCHAR(255) NOT NULL,
    free_quota_chars INTEGER NOT NULL DEFAULT 5000,
    created_at       TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_users_email ON users (email);

CREATE TABLE IF NOT EXISTS plans (
    id                       VARCHAR(36) PRIMARY KEY,
    name                     VARCHAR(80) NOT NULL,
    interval                 VARCHAR(16) NOT NULL,   -- month | year | payg
    price_cents              INTEGER NOT NULL DEFAULT 0,
    chars_per_period         INTEGER NOT NULL DEFAULT 0,
    overage_price_per_kchar  INTEGER NOT NULL DEFAULT 0,
    duration_days            INTEGER NOT NULL DEFAULT 30,
    active                   BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id            VARCHAR(36) PRIMARY KEY,
    user_id       VARCHAR(36) NOT NULL REFERENCES users (id),
    plan_id       VARCHAR(36) NOT NULL REFERENCES plans (id),
    status        VARCHAR(16) NOT NULL DEFAULT 'active',
    period_start  TIMESTAMP NOT NULL DEFAULT now(),
    period_end    TIMESTAMP,
    granted_chars INTEGER NOT NULL DEFAULT 0,
    used_chars    INTEGER NOT NULL DEFAULT 0,
    auto_renew    BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions (user_id);

CREATE TABLE IF NOT EXISTS usages (
    id           VARCHAR(36) PRIMARY KEY,
    user_id      VARCHAR(36) NOT NULL REFERENCES users (id),
    session_id   VARCHAR(64) NOT NULL,
    started_at   TIMESTAMP NOT NULL DEFAULT now(),
    ended_at     TIMESTAMP,
    in_tokens    INTEGER NOT NULL DEFAULT 0,
    out_tokens   INTEGER NOT NULL DEFAULT 0,
    image_tokens INTEGER NOT NULL DEFAULT 0,
    chars_billed INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_usages_user_id ON usages (user_id);
CREATE INDEX IF NOT EXISTS ix_usages_session_id ON usages (session_id);

CREATE TABLE IF NOT EXISTS orders (
    id              VARCHAR(36) PRIMARY KEY,
    user_id         VARCHAR(36) NOT NULL REFERENCES users (id),
    subscription_id VARCHAR(36) REFERENCES subscriptions (id),
    plan_id         VARCHAR(36) REFERENCES plans (id),
    channel         VARCHAR(16) NOT NULL DEFAULT 'wechat',
    amount_cents    INTEGER NOT NULL DEFAULT 0,
    chars_granted   INTEGER NOT NULL DEFAULT 0,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
    out_trade_no    VARCHAR(64) UNIQUE NOT NULL,
    paid_at         TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    raw             TEXT
);
CREATE INDEX IF NOT EXISTS ix_orders_user_id ON orders (user_id);
CREATE INDEX IF NOT EXISTS ix_orders_out_trade_no ON orders (out_trade_no);
