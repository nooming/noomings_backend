# -*- coding: utf-8 -*-
"""
noomings 后端入口（Citywalk + Parking 共用 Flask 应用）。
业务逻辑见 planning/、agent/、lib/、parking/、api/。
"""
import logging
import os
import sys
from pathlib import Path

from flask import Flask, jsonify
from flask_sock import Sock

_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_ROOT / ".env")
except ImportError:
    pass

from api.cors import apply_cors
from lib.amap_client import get_amap_key
from planning import runtime as planning_runtime

# 高德 Key 须在 import planning.route_engine / plan_service 前注入
planning_runtime.AMAP_KEY = os.environ.get("AMAP_KEY", "").strip() or get_amap_key() or ""
planning_runtime.AMAP_STATIC_MAP_KEY = (
    os.environ.get("AMAP_STATIC_MAP_KEY", "").strip() or planning_runtime.AMAP_KEY
)
AMAP_KEY = planning_runtime.AMAP_KEY
AMAP_STATIC_MAP_KEY = planning_runtime.AMAP_STATIC_MAP_KEY

if not AMAP_KEY:
    logging.warning("未配置 AMAP_KEY，路线规划接口将不可用")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_FRONTEND_ROOT = (_BACKEND_ROOT.parent / "frontend").resolve()
_SERVE_FRONTEND = _FRONTEND_ROOT.is_dir()
_static_folder = str(_FRONTEND_ROOT) if _SERVE_FRONTEND else None
app = Flask(__name__, static_folder=_static_folder, static_url_path="")
apply_cors(app)
sock = Sock(app)


@app.route("/")
def index():
    """主页；无 frontend 时返回 API 指引。"""
    if not _SERVE_FRONTEND:
        return jsonify({
            "service": "noomings-backend",
            "apps": {
                "citywalk": "https://nooming.github.io/app/citywalk/",
                "parking-pso": "https://nooming.github.io/app/parking-pso/",
            },
            "api": {
                "health": "/api/health",
                "citywalk": "/api/citywalk/",
                "parking": "/api/parking/",
            },
        }), 200
    html_path = _FRONTEND_ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")
    js_key = os.environ.get("AMAP_JS_KEY", "").strip()
    sec = os.environ.get("AMAP_JS_SECURITY_CODE", "").strip()
    html = html.replace("__AMAP_JS_KEY__", js_key)
    html = html.replace("__AMAP_JS_SECURITY_CODE__", sec)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


from api import register_blueprints  # noqa: E402

register_blueprints(app, sock)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
