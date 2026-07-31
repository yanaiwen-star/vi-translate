-- vi-translate: 免费同传额度从「每日 N 分钟（次日重置）」改为「一次性 N 分钟（终身累计）」
--
-- 背景：原实现把已用量记在 Redis key `free_daily:{user_id}:{YYYY-MM-DD}`，
-- 天然按天重置。改成一次性额度后，已用量必须永久保存：
--   1) 跨天不能清零；
--   2) 不能放 Redis —— 生产 Redis 用 allkeys-lru 淘汰策略，永久 key 可能被逐出，
--      会让用完的免费额度「复活」。
-- 因此落到 users 表。
--
-- 迁移是向前兼容的：新列带默认值 0，存量用户视为「免费额度一点没用过」，
-- 即每人获得一次全新的 30 分钟。若要按历史用量扣减，见文件末尾的可选语句。

ALTER TABLE users ADD COLUMN IF NOT EXISTS free_total_used_chars INTEGER NOT NULL DEFAULT 0;

-- 可选：把存量用户的历史同传消耗回填为免费额度已用量（上限 30 分钟 = 60000 字符）。
-- 默认不执行——按「上线即人人重新赠送 30 分钟」的运营口径处理更简单。
-- 如需回填，取消下面的注释后执行：
--
-- UPDATE users u
-- SET free_total_used_chars = LEAST(
--       COALESCE((SELECT SUM(chars_billed) FROM usages WHERE user_id = u.id), 0),
--       60000
--     );
