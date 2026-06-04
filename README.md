# Citywalk 本地启动说明

全国 Citywalk 定制路线规划 Web 应用。仓库根目录仅 **`backend/`**（本目录，Zeabur 部署单元）与 **`frontend/`**（静态页）。

## 环境要求

- Python 3.9+（建议 3.10 及以上）
- 可访问外网（调用高德地图、DeepSeek 等接口）
- 高德开放平台 Key（地理编码、步行路径、周边搜索等）
- DeepSeek API Key（智能规划 / 对话 / 导览文案，可选但推荐）

## 一、配置 backend

在本目录安装依赖：

```powershell
cd backend
pip install -r requirements.txt
```

复制环境变量模板并填写密钥：

```powershell
copy .env.example .env
```

编辑 `backend/.env`，至少配置：

| 变量 | 说明 |
|------|------|
| `AMAP_KEY` | 高德 Web 服务 Key（路线规划、POI 等，**必填**） |
| `AMAP_STATIC_MAP_KEY` | 高德静态地图 Key（分享图，可与上相同） |
| `AMAP_JS_KEY` | 前端地图 JS Key（填入后由首页注入，须配置域名白名单） |
| `AMAP_JS_SECURITY_CODE` | 高德 JS API 安全密钥（与 JS Key 配套） |
| `CORS_ORIGINS` | 生产跨域白名单（逗号分隔、无空格）。须含 `https://noomings.com` 与 `https://nooming.github.io` 等实际访问域；本地可留空 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（智能体功能） |
| `PORT` | 后端端口，默认 `5000` |
| `FLASK_DEBUG` | 本地调试可设为 `true`，生产请 `false` |

灵感种草·联网选点（可选，留空则用 LLM 自身知识选点）：

| 变量 | 说明 |
|------|------|
| `CW_INSPIRATION_PROVIDER` | 选点来源：默认 `llm`；设为 `web_search` 启用真·联网搜索 grounding |
| `CW_SEARCH_PROVIDER` | 搜索后端，默认 `tavily`（备选 `serper` / `brave`，需各自 key） |
| `TAVILY_API_KEY` | Tavily 搜索 Key（[tavily.com](https://tavily.com) 免费额度约 1000 次/月）；**留空时自动回退 LLM 选点，不报错** |

> 勿将 `.env` 提交到 Git。高德控制台请为 Key 配置合适的服务与白名单。

## 二、启动方式（二选一）

### 方式 A：只启 backend（推荐，最简单）

monorepo 下 backend 会挂载同级 `frontend/`，启动后可直接打开页面：

```powershell
cd backend
python citywalk.py
```

浏览器访问：**http://localhost:5000/** 或 **http://127.0.0.1:5000/**

此时前端会自动把 API 指向 `http://localhost:5000`（见 `frontend/assets/js/core/cw-state.js`）。

### 方式 B：backend + 独立静态服务

适合只改前端、用 8080 端口调试的情况。

**终端 1 — backend：**

```powershell
cd backend
python citywalk.py
```

**终端 2 — frontend 静态服务（在项目根目录）：**

```powershell
cd frontend
python -m http.server 8080
```

浏览器访问：**http://localhost:8080/index.html**

> 必须通过 `http://localhost` 或 `http://127.0.0.1` 打开，**不要**用 `file://` 直接打开 HTML，否则接口会指向线上 Zeabur 而非本地 backend。

## 三、验证是否启动成功

1. backend：终端无报错，监听 `0.0.0.0:5000`（或 `.env` 中的 `PORT`）。
2. 页面：地图可加载，选择城市后能规划路线。
3. 智能体：在输入框用自然语言规划；若未配置 `DEEPSEEK_API_KEY`，智能相关接口可能失败，传统表单规划仍依赖高德 Key。

常用接口（本地默认 `http://localhost:5000`）：

- `POST /plan` — 路线规划
- `GET /locate_city` — 定位城市
- `POST /agent/plan_once`、`POST /agent/chat`、`POST /agent/guide` — 智能体

## 四、目录结构（简要）

```
citywalk/
├── backend/       # citywalk.py、agent/、lib/、planning/、tests/（Zeabur Root）
└── frontend/      # index.html、assets/（GitHub Pages 或本地静态）
```

## 五、Zeabur 部署

| 项 | 值 |
|----|-----|
| Root Directory | `backend` |
| Start Command | `python citywalk.py` |
| 生产 UI | https://nooming.github.io/app/citywalk/ |
| API | https://noomings-backend.zeabur.app |

仅部署 `backend/` 时无同级 `frontend/`，访问 `/` 返回 JSON 指引；请在 `CORS_ORIGINS` 中配置前端域名（含自定义域 `noomings.com` 与 `nooming.github.io`）。

**发布前检查：**

1. 将本目录整包（`citywalk.py`、`agent/`、`lib/`、`planning/`、`api/`、`tests/` 等）同步到 **noomings_backend**；若对方仍为扁平布局，至少同步 `citywalk.py` 并带上 `lib/`、`planning/` 子包。
2. Zeabur 环境变量按 `.env.example` 配置；`CORS_ORIGINS` 示例：`https://noomings.com,https://www.noomings.com,https://nooming.github.io,https://www.nooming.github.io`
3. 仅部署 `backend/` 时无需上传 `frontend/`。

仓库根保留 `frontend/` 时，本地 `python citywalk.py` 仍可在 `:5000` 提供完整静态页。

## 六、常见问题

| 现象 | 处理 |
|------|------|
| 页面能开但规划一直失败 | 检查 `AMAP_KEY` 是否有效、额度与白名单 |
| 提示「请求过于频繁」/ CUQPS | 稍等 30 秒再试；可调低 `AMAP_MAX_CONCURRENT` 或升级高德配额 |
| 地图空白 | 配置 `AMAP_JS_KEY` 与 `AMAP_JS_SECURITY_CODE` 后重启 backend |
| 智能规划报 500 / 密钥错误 | 检查 `DEEPSEEK_API_KEY` 与网络；查看终端日志 |
| 本地仍请求线上 API | 确认用 `localhost` 访问，且 hostname 为 `localhost` / `127.0.0.1` |
| 端口被占用 | 修改 `.env` 中 `PORT`，或关闭占用 5000 端口的进程 |
