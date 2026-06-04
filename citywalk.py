# -*- coding: utf-8 -*-
"""
Citywalk 后端入口（Flask 装配 + 路由注册）。
业务逻辑见 planning/、lib/、agent/、api/。
"""
import logging
import os
import sys
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_ROOT / ".env")
except ImportError:
    pass

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


def _cors_origins() -> list:
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["*"]


_CORS_RESOURCE = {
    "origins": _cors_origins(),
    "methods": ["GET", "POST", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
    "supports_credentials": False,
}
CORS(app, resources={
    r"/api/*": _CORS_RESOURCE,
    r"/plan": _CORS_RESOURCE,
    r"/resolve_location": _CORS_RESOURCE,
    r"/config/*": _CORS_RESOURCE,
    r"/locate_city": _CORS_RESOURCE,
    r"/search_image": _CORS_RESOURCE,
    r"/agent/*": _CORS_RESOURCE,
    r"/poi/*": _CORS_RESOURCE,
})


@app.route("/")
def index():
    """主页；无 frontend 时返回 API 指引。"""
    if not _SERVE_FRONTEND:
        return jsonify({
            "service": "citywalk-api",
            "ui": "https://nooming.github.io/app/citywalk/",
        }), 200
    html_path = _FRONTEND_ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")
    js_key = os.environ.get("AMAP_JS_KEY", "").strip()
    sec = os.environ.get("AMAP_JS_SECURITY_CODE", "").strip()
    html = html.replace("__AMAP_JS_KEY__", js_key)
    html = html.replace("__AMAP_JS_SECURITY_CODE__", sec)
    return html, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/config/public", methods=["GET", "OPTIONS"])
def config_public():
    if request.method == "OPTIONS":
        return jsonify({"success": True})
    return jsonify({
        "success": True,
        "amap_js_key": os.environ.get("AMAP_JS_KEY", "").strip(),
        "amap_js_security_code": os.environ.get("AMAP_JS_SECURITY_CODE", "").strip(),
    })


from api import register_blueprints  # noqa: E402

register_blueprints(app)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
