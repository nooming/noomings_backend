# noomings 后端（Citywalk + Parking）

Zeabur 统一部署单元：`app.py` 同时提供 **Citywalk** 路线规划与 **停车方案设计器** API。

| 应用 | 前端 Pages | API 前缀 |
|------|------------|----------|
| Citywalk | https://nooming.github.io/app/citywalk/ | `/api/citywalk/*` |
| Parking | https://nooming.github.io/app/parking-pso/ | `/api/parking/*` |
| 公共 | — | `/api/health`、`/api/config/public` |

线上 API：**https://noomings-backend.zeabur.app**

## 环境要求

- Python 3.9+（建议 3.10 及以上）
- 可访问外网（调用高德地图、DeepSeek 等接口）
- 高德开放平台 Key（地理编码、步行路径、周边搜索等）
- DeepSeek API Key（智能规划 / 对话 / 导览文案，可选但推荐）

## 一、配置

在本目录（仓库根）安装依赖：

```powershell
cd noomings_backend
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`，至少配置：

| 变量 | 说明 |
|------|------|
| `AMAP_KEY` | 高德 Web 服务 Key（路线规划、POI 等，**必填**） |
| `AMAP_STATIC_MAP_KEY` | 高德静态地图 Key（分享图，可与上相同） |
| `AMAP_JS_KEY` | 前端地图 JS Key（填入后由配置 API 提供，须配置域名白名单） |
| `AMAP_JS_SECURITY_CODE` | 高德 JS API 安全密钥（与 JS Key 配套） |
| `CORS_ORIGINS` | 生产跨域白名单（逗号分隔、无空格）。须含 `https://noomings.com` 与 `https://nooming.github.io` 等实际访问域；本地可留空 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（智能体功能） |
| `PORT` | 后端端口，默认 `5000` |
| `FLASK_DEBUG` | 本地调试可设为 `true`，生产请 `false` |
| `DATABASE_PATH` | Parking 方案库 SQLite，默认 `./parking/data/parking_pso.db`；Zeabur 建议 `/data/parking_pso.db` + Volume |

灵感种草·联网选点（可选）：

| 变量 | 说明 |
|------|------|
| `CW_INSPIRATION_PROVIDER` | 选点来源：默认 `llm`；设为 `web_search` 启用联网搜索 |
| `CW_SEARCH_PROVIDER` | 搜索后端，默认 `tavily` |
| `TAVILY_API_KEY` | Tavily 搜索 Key；留空时自动回退 LLM 选点 |

> 勿将 `.env` 提交到 Git。

## 二、启动

```powershell
cd noomings_backend
python app.py
```

浏览器访问：**http://localhost:5000/**（返回 JSON 服务指引）。独立静态前端用 `localhost` 打开 Pages 副本，API 自动指向 `http://localhost:5000`。

## 三、验证

1. `GET /api/health` → `{"ok": true, "services": ["citywalk", "parking"]}`
2. Citywalk：`POST /api/citywalk/plan`、`GET /api/citywalk/locate_city`
3. Parking：`GET /api/parking/scenarios`、`POST /api/parking/optimize`
4. 测试：`python -m pytest -q`

## 四、目录结构

根目录仅两个产品域文件夹；CORS 与 `/api/health` 在 `app.py`，高德 Key 注入在 `citywalk/bootstrap.py`。

```
noomings_backend/
├── app.py                      # Flask 入口、CORS、/api/health
├── pytest.ini, requirements.txt, .env.example
├── citywalk/                   # Citywalk 产品域
│   ├── api/                    # /api/citywalk/* 与 /api/config/public
│   ├── core/                   # planning/ agent/ geo/
│   ├── bootstrap.py            # 高德 Key 启动注入
│   └── tests/
└── parking/                    # 停车方案设计器（parking-pso）
    ├── api/                    # /api/parking/* 路由与 WebSocket
    ├── core/                   # optimizer/ planner/ simulator/ storage/
    ├── data/                   # parking_pso.db（本地默认路径）
    └── tests/
```

## 五、Citywalk 模块说明

Citywalk 提供城市步行路线规划，支持直接规划与 LLM 智能体两条路径，共用同一套规划引擎。

| 目录 | 职责 |
|------|------|
| `api/` | Flask 蓝图，HTTP 请求解析与响应封装 |
| `core/planning/` | 路线引擎：POI 选点、路径计算、时间预算、循环路线 |
| `core/agent/` | LLM 编排：意图解析、对话、种草、导览文案 |
| `core/geo/` | 高德 Web API 客户端、地理编码、距离/城市工具 |

- **直接规划**：`POST /api/citywalk/plan` → `execute_plan_request()`（`core/planning/plan_service.py`）
- **智能体规划**：`/api/citywalk/agent/*` → `parse_plan_intent()` → 仍调用 `execute_plan_request()`
- **外部依赖**：高德地图（`core/geo/`）、DeepSeek（`core/agent/llm_client.py`）、Tavily 可选（联网选点）

## 六、Parking 模块说明

`parking`（产品名 parking-pso）提供场景管理、PSO 优化、自动车位规划与模拟，支持异步任务与 WebSocket 进度推送。

| 目录 | 职责 |
|------|------|
| `api/` | Flask 蓝图与 WebSocket 任务流 |
| `core/optimizer/` | PSO 粒子群优化、路径代价、匈牙利分配 |
| `core/planner/` | 自动车位/方案建议 |
| `core/simulator/` | 场景运行模拟 |
| `core/storage/` | SQLite 方案库与任务状态（默认 `parking/data/parking_pso.db`） |

主要端点：`/api/parking/scenarios`（CRUD）、`/api/parking/optimize`（PSO）、`/api/parking/simulate` + WebSocket 进度流。Golden 测试见 `parking/tests/fixtures/default-scenario.json`。

## 七、Zeabur 部署

| 项 | 值 |
|----|-----|
| Root Directory | 仓库根（本目录） |
| Start Command | `python app.py` |
| 生产 UI（Citywalk） | https://nooming.github.io/app/citywalk/ |
| 生产 UI（Parking） | https://nooming.github.io/app/parking-pso/ |
| API | https://noomings-backend.zeabur.app |

`CORS_ORIGINS` 示例：`https://noomings.com,https://www.noomings.com,https://nooming.github.io,https://www.nooming.github.io`

## 八、常见问题

| 现象 | 处理 |
|------|------|
| 页面能开但规划一直失败 | 检查 `AMAP_KEY` 是否有效、额度与白名单 |
| 提示「请求过于频繁」/ CUQPS | 稍等 30 秒再试；可调低 `AMAP_MAX_CONCURRENT` |
| 地图空白 | 配置 `AMAP_JS_KEY` 与 `AMAP_JS_SECURITY_CODE` |
| Parking 方案库不持久 | 检查 `DATABASE_PATH` 与 Zeabur Volume |
| 本地仍请求线上 API | 确认用 `localhost` 访问前端 |
