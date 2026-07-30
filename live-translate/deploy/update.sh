#!/usr/bin/env bash
# ============================================================
# vi-translate v2 - 零停机更新脚本
# 用法: cd /opt/vi-translate/deploy && sudo -u admin bash update.sh
# 流程: 拉代码 -> 重建 app 镜像 -> up -d --no-deps app -> 健康检查
# ============================================================
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}[ OK ]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
fail() { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

# 必须由 admin 跑（脚本里 docker 命令走 sudo -u admin）
COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$COMPOSE_DIR")"
ADMIN_USER="admin"

# --- 1. 拉取最新代码 ---
log "==== [1/4] 拉取最新代码 ===="
if [ -d "$PROJECT_DIR/.git" ]; then
    cd "$PROJECT_DIR"
    sudo -u "$ADMIN_USER" git pull --rebase --autostash
    ok "git pull 完成"
else
    warn "无 .git 目录，跳过拉取（请手动 scp 覆盖代码后再跑）"
fi

# --- 2. 重建 app 镜像 ---
log "==== [2/4] 重建 app 镜像 ===="
cd "$COMPOSE_DIR"
sudo -u "$ADMIN_USER" docker compose build app
ok "镜像重建完成"

# --- 3. 零停机重启（仅 app 容器） ---
log "==== [3/4] 零停机重启 app 容器 ===="
sudo -u "$ADMIN_USER" docker compose up -d --no-deps app
# 清理旧镜像（避免磁盘占满）
sudo -u "$ADMIN_USER" docker image prune -f
ok "app 已重启"

# --- 4. 健康检查 ---
log "==== [4/4] 健康检查 ===="
HEALTH_OK=0
for i in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf http://localhost/healthz > /dev/null 2>&1; then
        HEALTH_OK=1
        ok "健康检查通过 (尝试 $i 次)"
        break
    fi
    sleep 3
done

if [ $HEALTH_OK -eq 0 ]; then
    fail "健康检查失败，查看日志:
    cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose logs --tail=50 app"
fi

echo ""
ok "更新完成"
echo "  状态: cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose ps"
echo "  日志: cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose logs -f --tail=100"
