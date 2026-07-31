-- vi-translate: 绑定奖励（昵称 +10 分钟 / 手机号 +20 分钟，一次性不重复送）
--
-- 背景：
--   1) 注册赠送改走「一次性免费墙钟池」users.free_total_used_chars（见 0006），
--      因此 free_quota_chars 不再默认送 5000，必须对齐为 0，否则新用户会
--      凭空多拿 2.5 分钟（5000/2000）。存量用户若仍是旧默认值 5000 也一并清零。
--   2) 新增两个防重发标记，绑定奖励只发一次：
--        nickname_reward_given  -> 设置昵称发 +10 分钟
--        phone_reward_given     -> 绑定手机发 +20 分钟
--      奖励金额都记入 users.free_quota_chars（与运营手动赠送同一池，字符等值累加）。
--
-- 换算：1 分钟同传 ≈ 2000 字符（CHARS_PER_MINUTE）。奖励在后端常量里定义，
-- 此处只负责落列与默认值，金额换算由 app/billing/quota.py 完成。

-- 1) free_quota_chars 默认值 5000 -> 0（与 models.py default=0 对齐）
ALTER TABLE users ALTER COLUMN free_quota_chars SET DEFAULT 0;

-- 存量用户若仍是旧默认值 5000（即从未被运营手动调整过），清零避免凭空多送。
-- 若某用户确实被后台手动赠送过（值 != 5000），保持原值不动。
UPDATE users SET free_quota_chars = 0 WHERE free_quota_chars = 5000;

-- 2) 绑定奖励防重发标记（PostgreSQL 布尔列默认须用 false，不能写整数 0）
ALTER TABLE users ADD COLUMN IF NOT EXISTS nickname_reward_given BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_reward_given BOOLEAN NOT NULL DEFAULT false;
