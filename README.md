# 越南语同传小程序 (vi-translate)

> 中越双向同声传译微信小程序 — 边说边译，自动判别语种

> ⚠️ **项目状态**：骨架已搭建（v0.1.0 MVP）。微信开发者工具可直接打开 `miniprogram/` 目录。

## ✨ 核心特性

- 🎙️ **双向自动同传**：左右分栏，无需手动切换语种
- ⚡ **流式识别**：松开自动触发识别+翻译+TTS 朗读
- 🔊 **多音色**：中文/越南语，男女声可选
- 📜 **历史回放**：每轮对话自动存档
- 🆓 **每日免费 5 分钟**

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 前端 | 微信小程序原生（WXML + WXSS + JS） |
| 后端 | 腾讯云 CloudBase（云函数 + NoSQL） |
| ASR | 腾讯云一句话识别（支持中越自动判别） |
| MT  | 腾讯云文本翻译 TMT（中↔越） |
| TTS | 腾讯云短文本语音合成（中↔越音色） |

## 📦 已搭建内容

### 前端（`miniprogram/`）
- ✅ `app.{js,json,wxss}` — 全局配置 + CloudBase 初始化
- ✅ `pages/index/` — 同传主页（会议模式左右分栏）
- ✅ `pages/history/` — 历史记录列表 + 详情
- ✅ `pages/profile/` — 个人中心（配额 + 设置）
- ✅ `components/chat-bubble/` — 聊天气泡组件
- ✅ `components/lang-badge/` — 语种标识组件
- ✅ `utils/recorder.js` — PCM 录音 + 音量计算
- ✅ `utils/asr.js` — ASR 调用封装
- ✅ `utils/mt.js` — 翻译调用封装
- ✅ `utils/tts.js` — TTS 调用 + 音频播放
- ✅ `utils/session.js` — 会话/历史持久化
- ✅ `utils/lang-detect.js` — 语种辅助
- ✅ `images/tab-*.png` — tabBar 图标（6 个）

### 后端（`cloudfunctions/`）
- ✅ `asr/` — 语音识别（调腾讯云 ASR）
- ✅ `mt/` — 文本翻译（调腾讯云 TMT）
- ✅ `tts/` — 语音合成（调腾讯云短文本 TTS）
- ✅ `common/` — 公共能力（openid / 会话 / 消息 / 配额）

### 文档（`docs/`）
- ✅ `ARCHITECTURE.md` — 架构设计
- ✅ `API.md` — API 对接说明

## 📁 目录结构

```
vi-translate/
├── miniprogram/                # 微信小程序前端（开发者工具打开此目录）
│   ├── app.{js,json,wxss}
│   ├── pages/
│   │   ├── index/              # 同传主页（会议模式）
│   │   ├── history/            # 历史记录
│   │   └── profile/            # 个人中心
│   ├── components/
│   │   ├── chat-bubble/
│   │   └── lang-badge/
│   ├── utils/                  # 录音/ASR/MT/TTS/会话
│   └── images/                 # tabBar 图标
├── cloudfunctions/             # 云函数（上传到 CloudBase）
│   ├── asr/                    # 语音识别
│   ├── mt/                     # 翻译
│   ├── tts/                    # 语音合成
│   └── common/                 # 公共（openid / 会话 / 消息）
├── docs/
│   ├── ARCHITECTURE.md
│   └── API.md
├── scripts/
│   └── gen-icons.js            # tabBar 图标生成器
└── README.md
```

## 🚀 启动步骤

### 1. 安装微信开发者工具
下载地址：https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html

### 2. 导入项目
- 打开开发者工具 → 导入项目
- 项目目录：`E:\vi-translate\miniprogram`
- AppID：`wxfabcc61911cff7f1`（已写入 `project.config.json`）

### 3. 关联 CloudBase 环境
- 工具栏 → 云开发 → 创建/关联环境 `trans-d4gi6y1yw8a309642`

### 4. 配置云函数环境变量
在 CloudBase 控制台 → 云函数 → 选中每个函数 → 函数配置 → 环境变量：

| 变量 | 值 | 必填 |
|---|---|---|
| `TENCENT_SECRET_ID` | `***REDACTED_TENCENT_SECRET_ID***` | ✅ |
| `TENCENT_SECRET_KEY` | `1xmSzOejXFm9VhjbMxNcAh4HNK9pMkzI` | ✅ |
| `WX_SECRET` | `172f3b3743ed2d9fc77079cb1381817d` | 可选 |

需要配置的云函数：`asr`, `mt`, `tts`, `common`

### 5. 上传云函数
对 `cloudfunctions/` 下每个新函数：
- 右键文件夹 → 上传并部署：云端安装依赖
- 等待依赖安装完成（首次约 1~2 分钟）

### 6. 创建数据库集合
在 CloudBase → 数据库 → 创建集合：
- `sessions`（会话）
- `messages`（消息）
- `quotas`（配额）

权限设置：仅创建者可读写

### 7. 真机测试
- 工具栏 → 预览 → 扫码
- 需两台手机测试双向同传（A 中文 / B 越南语）

## 🔧 已知同类云函数（已存在）

仓库里还保留了旧版本的同功能云函数，**两套并存**：
- 旧的：`tencent-asr/`、`tencent-tts/`、`translate/`（一步式）
- 新的：`asr/`、`mt/`、`tts/`、`common/`

前端 `utils/` 当前调用**新的**云函数。如需切换，修改 `miniprogram/utils/` 即可。

## 📅 开发进度

- [x] 项目骨架（前端 + 后端 + 文档）
- [ ] 真机调试 + 调优延迟
- [ ] 流式 ASR（VAD 触发）
- [ ] UI 细节打磨
- [ ] 会员订阅

## ⚠️ 注意事项

1. **首次录音前需授权麦克风权限**（代码已处理）
2. **TTS 返回的是 fileID**，播放前会自动转临时 URL
3. **越南语 ASR**用 `16k_zh` 引擎自动判别，要求清晰普通话/越南语
4. **每日配额**本地缓存 + 云端双重记录

## ⚖️ 许可

仅供学习和商务洽谈使用。