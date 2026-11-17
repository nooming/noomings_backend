# noomings 后端（Citywalk）

停车方案已迁移为纯本地前端（`app/parking-pso/`），本仓库只保留 **Citywalk** API。

## 环境要求

- Python 3.9+
- 可访问外网（高德地图、DeepSeek 可选）
- 高德开放平台 Key
- DeepSeek API Key（智能规划 / 对话 / 导览文案，可选）

## 一、配置

```powershell
cd noomings_backend
pip install -r requirements.txt
copy .env.example .env
```

编辑 `.env`，至少配置：

| 变量 | 说明 |
|---|---|
| `AMAP_KEY` | 高德 Web 服务 Key（路线规划、POI 等，必填） |
| `AMAP_STATIC_MAP_KEY` | 高德静态地图 Key（分享图，可与上相同） |
| `AMAP_JS_KEY` | 前端地图 JS Key |
| `AMAP_JS_SECURITY_CODE` | 高德 JS API 安全密钥 |
| `CORS_ORIGINS` | 生产跨域白名单，例如 `https://noomings.com,https://www.noomings.com` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key（智能体功能，可选） |
| `PORT` | 后端端口，默认 5000；容器内为 8080 |
| `FLASK_DEBUG` | 生产请设为 `false` |

> 勿将 `.env` 提交到 Git。

## 二、启动

```powershell
cd noomings_backend
python app.py
```

浏览器访问 `http://localhost:5000/` 应返回服务指引。

## 三、验证

1. `GET /api/health` → `{"ok": true, "services": ["citywalk"]}`
2. Citywalk：`POST /api/citywalk/plan`、`GET /api/citywalk/locate_city`
3. 测试：`python -m pytest -q`

## 四、目录结构

```text
noomings_backend/
├── app.py                  # Flask 入口、CORS、/api/health
├── citywalk/
│   ├── api/                # /api/citywalk/* 与 /api/config/public
│   ├── core/               # planning / agent / geo
│   ├── bootstrap.py        # 高德 Key 注入
│   └── tests/
└── requirements.txt
```

## 五、Citywalk 模块

| 目录 | 职责 |
|---|---|
| `citywalk/api/` | Flask 蓝图、HTTP 请求解析与响应封装 |
| `citywalk/core/planning/` | POI 选点、路径计算、时间预算、循环路线 |
| `citywalk/core/agent/` | LLM 编排：意图解析、对话、种草、导览文案 |
| `citywalk/core/geo/` | 高德 Web API 客户端、地理编码、距离/城市工具 |

- 直接规划：`POST /api/citywalk/plan`
- 智能体规划：`/api/citywalk/agent/*`

## 六、部署状态

当前 **暂缓部署**。`noomings.com` 只提供静态前端，Citywalk 未上线：

- 前端 `/app/citywalk/` 返回 404
- 没有 `api.noomings.com`
- 不启动容器，不占用服务器 8080
- 不恢复首页和顶栏入口

未来恢复时再补：

- 后端容器或进程
- 反向代理与 HTTPS
- `CORS_ORIGINS`
- 账号 / UGC 合规
- 公安备案与隐私说明

## 七、停车

停车已改为纯本地前端，不再调用本后端：

```text
app/parking-pso/
```

历史 Python 实现和数据库已删除，仅保留前端本地版本。
