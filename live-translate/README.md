# vi-translate（商业化 Web SaaS）

将本地实时翻译 demo 改造为对外「免费 + 收费」的网页服务：账号体系、按翻译字数
计量的配额/限流、微信支付订阅（¥19.9/月含字数池 + 超量按量）、摄像头图片 token 自动
计入，最终以 Docker 部署到云服务器（PostgreSQL + Redis + Nginx）。

## 目录结构

```
app/
  config.py          # 仅从环境变量读配置，无硬编码密钥
  db.py              # PostgreSQL(SQLAlchemy) + Redis 单例
  models.py          # users/plans/subscriptions/usages/orders
  main.py            # FastAPI 入口：CORS 白名单 + 请求体大小限制 + 静态页
  auth/              # 注册/登录/JWT/WebSocket 鉴权
  billing/           # 套餐目录、计量(字数换算)、配额(池+Redis 限流)、HTTP 路由
  payments/          # 微信支付 APIv3(Native+H5) + 订单幂等发货
  translate/proxy.py # 实时翻译 WebSocket 代理（服务端统一密钥 + 计量钩子）
static/              # 前端：login / pricing / checkout / dialog / index
migrations/0001_init.sql
deploy/              # Dockerfile / docker-compose.yml / nginx.conf
```

## 本地开发（Docker）

```bash
cp .env.example .env      # 填写 DASHSCOPE_API_KEY、JWT_SECRET 等
docker compose -f deploy/docker-compose.yml up --build
# 应用: http://localhost:8000  (/login.html 注册登录, /dialog 同传)
```

未安装 Docker 时，也可本地安装 PostgreSQL/Redis，并设置 `DATABASE_URL` / `REDIS_URL`
后直接 `uvicorn app.main:app --port 8000`。

## 计费口径

按上游 DashScope 的 token 用量计费（成本与收入 1:1 对齐），界面对外显示「翻译字数」
（≈1.5 汉字 / token）。免费 5000 字/月；¥19.9/月含 6 万字，超量 0.2 元/千字；按量 0.2 元/千字。

## 安全

- 服务端统一持有 DashScope 密钥，前端不再传 api_key。
- 密钥仅来自环境变量 / .env（已加入 .gitignore），绝不入库。
- 对话内容、令牌等敏感信息不写日志。
