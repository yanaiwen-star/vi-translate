# 悦翻译

**简体中文** | [English](README.en.md) | [Tiếng Việt](README.vi.md)

> 中越同声传译微信小程序 + 实时翻译后端服务
>
> 面向中越跨境场景的公益便民翻译工具：边说边译的实时同传、面对面双话筒对话、拍照翻译、文字翻译，以及免费的译员/业务对接目录。

## ✨ 功能一览

### 翻译能力（小程序「同传」页，四种模式内联切换）

| 模式 | 说明 | 收费 |
|------|------|------|
| 🎙️ **同传** | 实时同声传译：边说边出译文，基于 WebSocket 流式链路 | 每日免费 30 分钟，超出可购语音包 |
| 🗣️ **面对面** | 双话筒一人一句：两人各按住自己一侧话筒说话（PTT），对方一侧倒置显示译文，适合面对面交流 | 同上（复用同传链路） |
| 📷 **拍照翻译** | 拍照/选图识别并翻译图中文字（视觉大模型） | 免费（仅限频防滥用） |
| ✍️ **文字翻译** | 输入文本即时互译 | 免费（仅限频防滥用） |

### 便民目录（公益免费）

- 🔍 **找翻译**：译员/翻译公司免费入驻，支持 59 个语种、口译/笔译两类服务、20 个专业领域多选筛选
- 💼 **找业务**：发布翻译需求，按 语种 ∩ 服务 ∩ 领域 自动匹配推送给合适的译员
- 📚 **常用语**：中越常用语句库，配套语音朗读，覆盖出行、住宿、贸易等高频场景

### 产品原则

- 不收手机号、不代收翻译费，译员入驻永久免费
- 只有实时同传超出每日免费额度后计费（语音包 ¥9.9 / ¥19.9 / ¥49.9，对应 60 / 200 / 600 分钟，一次购买长期有效）

## 🛠️ 技术栈

| 层 | 技术 |
|----|------|
| 小程序前端 | 微信小程序原生（WXML / WXSS / JS），5-tab 结构 |
| 后端框架 | Python 3.13 + FastAPI + Uvicorn |
| 实时同传 | WebSocket 代理 → 阿里云 DashScope `qwen3.5-livetranslate-flash-realtime` |
| 拍照翻译 | `qwen-vl-plus`（视觉理解） |
| 文字翻译 | `qwen-plus` |
| 数据库 | PostgreSQL（生产）/ SQLite（本地开发），SQLAlchemy 2.0 |
| 缓存/限频 | Redis（生产）/ fakeredis（本地开发） |
| 认证 | 微信 openid 登录 + JWT，后台管理另有图形验证码 |
| 支付 | 微信虚拟支付（语音包） |
| 部署 | Docker Compose（app + postgres + redis） |

## 📁 目录结构

```
vi-translate/
├── miniprogram/                  # 微信小程序前端（开发者工具打开此目录）
│   ├── app.{js,json,wxss}        # 全局配置（5-tab：同传/找翻译/找业务/常用语/我的）
│   ├── pages/
│   │   ├── index/                # 同传主页（同传/面对面/拍照/文字 四模式内联）
│   │   ├── services/             # 找翻译（译员目录 + 筛选）
│   │   ├── translator-detail/    #   └─ 译员详情
│   │   ├── translator-edit/      #   └─ 译员入驻/编辑资料
│   │   ├── business-publish/     # 找业务（发布翻译需求）
│   │   ├── matched-needs/        #   └─ 匹配到我的需求
│   │   ├── my-needs/             #   └─ 我发布的需求
│   │   ├── ask/                  # 常用语（分类语句 + 语音）
│   │   ├── profile/              # 我的（用户 ID / 配额 / 设置）
│   │   ├── pricing/ pay/         # 语音包购买
│   │   ├── history/              # 翻译历史
│   │   └── face/                 # 面对面独立页（备用，主入口已内联进 index）
│   ├── utils/
│   │   ├── live.js               # 同传 WebSocket 客户端（connect/finish/stop）
│   │   ├── recorder.js           # PCM 录音
│   │   └── ...
│   └── components/               # 通用组件
│
├── live-translate/               # 后端服务（FastAPI）
│   ├── app/
│   │   ├── main.py               # 应用入口
│   │   ├── config.py             # 配置（免费额度/限频等）
│   │   ├── models.py             # SQLAlchemy 模型
│   │   ├── translate/proxy.py    # 实时同传 WebSocket 代理（核心）
│   │   ├── photo/                # 拍照翻译 + 文字翻译 API
│   │   ├── directory/            # 找翻译/找业务目录（含权威语种/领域目录 catalog.py）
│   │   ├── auth/                 # 微信登录 / JWT / 短信
│   │   ├── billing/              # 配额与语音包套餐
│   │   ├── payments/             # 微信虚拟支付
│   │   ├── admin/                # 后台管理 API
│   │   └── sessions/ security/   # 会话与安全
│   ├── migrations/               # SQL 迁移脚本
│   ├── static/                   # 后台管理页 / 常用语音频等静态资源
│   ├── tests/                    # pytest 测试套件
│   ├── deploy/                   # Docker Compose 部署脚本
│   ├── requirements.txt
│   ├── run.ps1                   # Windows 本地一键启动
│   └── .env.example              # 环境变量模板
│
└── README.md
```

## 🚀 如何运行

### 一、后端（本地开发）

本地模式使用 SQLite + fakeredis，无需 Docker / PostgreSQL / Redis。

```bash
cd live-translate

# 1. 创建虚拟环境（Python 3.13）
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填入 DASHSCOPE_API_KEY（https://dashscope.console.aliyun.com/apiKey 申请）

# 4. 启动
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Windows 也可直接: .\run.ps1
```

启动后访问 `http://127.0.0.1:8000/healthz` 应返回 ok。

### 二、后端（生产部署）

```bash
cd live-translate/deploy
cp ../.env.example .env   # 填入生产配置（setup.sh 会自动生成强随机密码/密钥）
./setup.sh                # 首次部署：拉起 app + postgres + redis
./update.sh               # 后续更新：重建并重启
```

### 三、小程序前端

1. 打开 **微信开发者工具**，导入项目，目录选 `miniprogram/`
2. 填入自己的小程序 AppID（或选「测试号」体验）
3. 修改 `miniprogram/utils/` 下的后端地址为你部署的域名（生产需在微信公众平台配置 request / socket 合法域名，且必须 HTTPS / WSS）
4. 编译运行即可在模拟器体验；真机预览需扫码

### 环境变量说明（关键项）

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key（必填，同传/拍照/文字翻译共用） |
| `TRANSLATE_MODEL` | 同传模型，默认 `qwen3.5-livetranslate-flash-realtime` |
| `DATABASE_URL` | PostgreSQL 连接串（本地开发可不填，回落 SQLite） |
| `REDIS_URL` | Redis 连接串（本地开发可不填，回落 fakeredis） |
| `JWT_SECRET` | JWT 签名密钥（生产必须强随机） |
| `DIRECTORY_CONTACT_KEY` | 译员联系方式加密的 Fernet 密钥 |
| `FREE_DAILY_MINUTES` | 同传每日免费分钟数，默认 30 |

完整列表见 [`live-translate/.env.example`](live-translate/.env.example)。

## 🧪 测试

```bash
cd live-translate
pytest tests/
```

## 📄 许可

版权所有 © 悦迅翻译。代码公开供学习参考，商用请联系作者。

---

*悦翻译 —— 让中越沟通没有语言障碍。*
