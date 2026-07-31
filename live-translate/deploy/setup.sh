#!/usr/bin/env bash
# ============================================================
# vi-translate v2 - 一键部署脚本
# 适配: Alibaba Cloud Linux 3 (RHEL 8 系, dnf, SELinux)
# 用户: admin (sudo 免密)
# 用法: sudo bash setup.sh
#       或先 scp 上传代码到 /tmp/vi-translate 再 sudo bash /tmp/vi-translate/deploy/setup.sh
# ============================================================
set -euo pipefail

# --- 颜色 ---
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log()    { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
ok()     { echo -e "${GREEN}[ OK ]${NC} $*"; }
fail()   { echo -e "${RED}[FAIL]${NC} $*" >&2; exit 1; }

# --- 配置 ---
PROJECT_DIR="/opt/vi-translate"
COMPOSE_DIR="$PROJECT_DIR/deploy"
ADMIN_USER="admin"
PUBLIC_IP="${PUBLIC_IP:-$(hostname -I 2>/dev/null | awk '{print $1}')}"

# --- 1. 预检 ---
log "==== [1/8] 预检 ===="
if [ "$(id -u)" -ne 0 ]; then
    fail "必须以 root 或 sudo 运行此脚本"
fi
if ! command -v dnf &>/dev/null; then
    fail "未检测到 dnf（Alibaba Cloud Linux 3 必需），请确认系统类型"
fi
ok "系统: $(cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"')"
ok "公网 IP: $PUBLIC_IP"

# --- 2. 安装 Docker + compose plugin ---
log "==== [2/8] 检查/安装 Docker ===="
if ! command -v docker &>/dev/null; then
    log "安装 docker..."
    dnf install -y docker
    systemctl enable --now docker
    ok "docker 已安装并启动"
else
    ok "docker 已存在: $(docker --version)"
fi

if ! docker compose version &>/dev/null; then
    log "安装 docker-compose-plugin..."
    dnf install -y docker-compose-plugin
fi
ok "compose: $(docker compose version)"

# --- 3. 把 admin 加入 docker 组 ---
log "==== [3/8] 把 $ADMIN_USER 加入 docker 组 ===="
if id -nG "$ADMIN_USER" 2>/dev/null | grep -qw docker; then
    ok "$ADMIN_USER 已在 docker 组"
else
    usermod -aG docker "$ADMIN_USER"
    ok "$ADMIN_USER 已加入 docker 组（重新登录后免 sudo，当前用 sudo docker 跑命令）"
fi

# --- 4. SELinux 配置 ---
log "==== [4/8] SELinux 配置 ===="
if command -v getenforce &>/dev/null; then
    SELINUX_MODE=$(getenforce)
    case "$SELINUX_MODE" in
        Enforcing)
            log "SELinux Enforcing - 允许容器挂载目录..."
            setsebool -P container_manage_cgroup 1 2>/dev/null || true
            setsebool -P container_use_cephfs 1 2>/dev/null || true
            # 关键：允许容器读写 /opt/vi-translate
            if [ -d "$PROJECT_DIR" ]; then
                semanage fcontext -a -t container_file_t "$PROJECT_DIR(/.*)?" 2>/dev/null || \
                chcon -Rt container_file_t "$PROJECT_DIR" 2>/dev/null || \
                warn "无法自动设置 SELinux 上下文（如服务启动失败，请手动 chcon -R -t container_file_t $PROJECT_DIR）"
            fi
            ok "SELinux 已配置"
            ;;
        Permissive)
            ok "SELinux Permissive"
            ;;
        Disabled)
            ok "SELinux Disabled"
            ;;
    esac
else
    warn "未检测到 SELinux"
fi

# --- 5. 准备项目目录 ---
log "==== [5/8] 准备项目目录 $PROJECT_DIR ===="
mkdir -p "$PROJECT_DIR" "$COMPOSE_DIR/secrets" "$COMPOSE_DIR/nginx_logs"

# 如果当前目录有 app/deploy 目录，复制到 /opt（说明是 scp 上传的代码）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_BASE="$(dirname "$SCRIPT_DIR")"
if [ "$SOURCE_BASE" != "$PROJECT_DIR" ] && [ -d "$SOURCE_BASE/app" ] && [ -d "$SOURCE_BASE/deploy" ]; then
    log "从 $SOURCE_BASE 复制代码到 $PROJECT_DIR ..."
    cp -r "$SOURCE_BASE/app"     "$PROJECT_DIR/"
    cp -r "$SOURCE_BASE/deploy"   "$PROJECT_DIR/"
    cp -r "$SOURCE_BASE/static"   "$PROJECT_DIR/" 2>/dev/null || true
    cp -r "$SOURCE_BASE/migrations" "$PROJECT_DIR/" 2>/dev/null || true
    cp    "$SOURCE_BASE/requirements.txt" "$PROJECT_DIR/"
    cp    "$SOURCE_BASE/.dockerignore"   "$PROJECT_DIR/" 2>/dev/null || true
    cp    "$SOURCE_BASE/.env.example"    "$PROJECT_DIR/" 2>/dev/null || true
    ok "代码已复制"
elif [ -d "$PROJECT_DIR/app" ] && [ -d "$PROJECT_DIR/deploy" ]; then
    ok "项目目录已存在代码"
else
    fail "未找到项目代码，请确认 $PROJECT_DIR 下有 app/ deploy/ 目录"
fi

# --- 6. 生成 .env ---
log "==== [6/8] 生成 .env ===="
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    warn "$ENV_FILE 已存在，跳过生成（如要重置请先删除）"
else
    POSTGRES_PASSWORD=$(openssl rand -hex 24)
    JWT_SECRET=$(openssl rand -hex 48)
    QWEN_CREDENTIAL_KEY=$(openssl rand -base64 32 | tr '+/' '-_')
    # 优先从当前 shell 环境读 DASHSCOPE_API_KEY
    DASH_KEY="${DASHSCOPE_API_KEY:-}"

    cat > "$ENV_FILE" <<EOF
# vi-translate v2 - 部署环境变量
# 生成时间: $(date -Iseconds)
# 警告: 此文件含敏感凭据，权限 600，勿提交 git

# --- PostgreSQL ---
POSTGRES_USER=vi_translate
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=vi_translate
DATABASE_URL=postgresql+psycopg://vi_translate:$POSTGRES_PASSWORD@postgres:5432/vi_translate

# --- Redis ---
REDIS_URL=redis://redis:6379/0

# --- JWT ---
JWT_SECRET=$JWT_SECRET
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=30

# --- DashScope (通义/Qwen 实时翻译) ---
DASHSCOPE_API_KEY=$DASH_KEY
TRANSLATE_MODEL=qwen3.5-livetranslate-flash-realtime
QWEN_CREDENTIAL_KEY=$QWEN_CREDENTIAL_KEY

# --- HTTP ---
CORS_ORIGINS=http://$PUBLIC_IP,http://localhost
MAX_BODY_BYTES=8000000

# --- Billing ---
FREE_QUOTA_CHARS=5000
# 墙钟计费：每用户一次性免费同传分钟数（终身累计，用完不再重置）
FREE_TOTAL_MINUTES=30

# === WeChat Pay (备案后再启用) ===
# WECHAT_MCH_ID=
# WECHAT_APP_ID=
# WECHAT_API_V3_KEY=
# WECHAT_SERIAL_NO=
# WECHAT_PRIVATE_KEY_PATH=$COMPOSE_DIR/secrets/wechat_apiclient_key.pem
# WECHAT_NOTIFY_URL=
# WECHAT_PAY_PUBLIC_KEY=
# WECHAT_PAY_PUBLIC_KEY_ID=
EOF
    chmod 600 "$ENV_FILE"
    chown "$ADMIN_USER:$ADMIN_USER" "$ENV_FILE" 2>/dev/null || true
    ok ".env 已生成: $ENV_FILE"

    if [ -z "$DASH_KEY" ]; then
        warn "DASHSCOPE_API_KEY 未设置（实时翻译接口会被拒绝），部署完成后请编辑 $ENV_FILE 填入"
    fi
fi

# --- 7. 启动服务 ---
log "==== [7/8] 启动 Docker 服务 ===="
cd "$COMPOSE_DIR"
chown -R "$ADMIN_USER:$ADMIN_USER" "$PROJECT_DIR"

# 用 admin 跑 docker（已加 docker 组，但当前 shell 是 root，需要 newgrp 或显式 sudo -u）
sudo -u "$ADMIN_USER" docker compose pull 2>/dev/null || true
sudo -u "$ADMIN_USER" docker compose up -d --build
echo ""
sudo -u "$ADMIN_USER" docker compose ps
echo ""

# --- 8. 健康检查 ---
log "==== [8/8] 健康检查 ===="
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
    warn "健康检查 30 秒内未通过，查看日志："
    sudo -u "$ADMIN_USER" docker compose logs --tail=30
    warn "可手动: cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose logs -f"
fi

# --- 完成 ---
echo ""
echo -e "${GREEN}============================================================${NC}"
echo -e "${GREEN}  部署完成${NC}"
echo -e "${GREEN}============================================================${NC}"
echo ""
echo "  访问地址:  http://$PUBLIC_IP/"
echo "  项目目录:  $PROJECT_DIR"
echo "  .env 文件: $ENV_FILE"
echo ""
echo "  常用命令:"
echo "    # 查看状态:   cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose ps"
echo "    # 查日志:     cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose logs -f"
echo "    # 重启:       cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose restart"
echo "    # 更新代码:   cd $COMPOSE_DIR && sudo -u $ADMIN_USER bash update.sh"
echo ""
echo "  下一步:"
echo "    1. 编辑 $ENV_FILE 填入 DASHSCOPE_API_KEY"
echo "    2. cd $COMPOSE_DIR && sudo -u $ADMIN_USER docker compose restart app"
echo "    3. 浏览器访问 http://$PUBLIC_IP/ 测试"
echo "    4. 备案完成后，配置 HTTPS（见 nginx.conf 末尾注释）"
echo ""
