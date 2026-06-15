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
| `AMAP_JS_KEY` | 前端地图 JS Key（填入后由首页注入，须配置域名白名单） |
| `AMAP_JS_SECURITY_CODE` | 高德 JS API 安全密钥（与 JS Key 配套） |
| `CORS_ORIGINS` | 生产跨域白名单（逗号分隔、无空格）。须含 `https://noomings.com` 与 `https://nooming.github.io` 等实际访问域；本地可留空 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（智能体功能） |
| `PORT` | 后端端口，默认 `5000` |
| `FLASK_DEBUG` | 本地调试可设为 `true`，生产请 `false` |
| `DATABASE_PATH` | Parking 方案库 SQLite，默认 `./data/parking_pso.db`；Zeabur 建议 `/data/parking_pso.db` + Volume |

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

浏览器访问：**http://localhost:5000/**（若 monorepo 存在同级 `frontend/` 则托管 Citywalk 静态页；否则 `/` 返回 JSON 指引）。

独立静态前端调试时，用 `localhost` 打开 Pages 副本，API 自动指向 `http://localhost:5000`。

## 三、验证

1. `GET /api/health` → `{"ok": true, "services": ["citywalk", "parking"]}`
2. Citywalk：`POST /api/citywalk/plan`、`GET /api/citywalk/locate_city`
3. Parking：`GET /api/parking/scenarios`、`POST /api/parking/optimize`
4. 测试：`python -m pytest tests/ -q`

## 四、目录结构

```
noomings_backend/
├── app.py               # Flask 入口
├── api/
│   ├── cors.py
│   ├── routes_config.py
│   ├── citywalk/
│   └── parking/
├── planning/ agent/ lib/
├── parking/
└── tests/
```

## 五、Zeabur 部署

| 项 | 值 |
|----|-----|
| Root Directory | 仓库根（本目录） |
| Start Command | `python app.py` |
| 生产 UI（Citywalk） | https://nooming.github.io/app/citywalk/ |
| 生产 UI（Parking） | https://nooming.github.io/app/parking-pso/ |
| API | https://noomings-backend.zeabur.app |

`CORS_ORIGINS` 示例：`https://noomings.com,https://www.noomings.com,https://nooming.github.io,https://www.nooming.github.io`

## 六、常见问题

| 现象 | 处理 |
|------|------|
| 页面能开但规划一直失败 | 检查 `AMAP_KEY` 是否有效、额度与白名单 |
| 提示「请求过于频繁」/ CUQPS | 稍等 30 秒再试；可调低 `AMAP_MAX_CONCURRENT` |
| 地图空白 | 配置 `AMAP_JS_KEY` 与 `AMAP_JS_SECURITY_CODE` |
| Parking 方案库不持久 | 检查 `DATABASE_PATH` 与 Zeabur Volume |
| 本地仍请求线上 API | 确认用 `localhost` 访问前端 |
