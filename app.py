# -*- coding: utf-8 -*-
"""
noomings 后端入口（Citywalk + Parking 共用 Flask 应用）。
业务逻辑见 citywalk/、parking/。
"""
import logging
import os
import sys
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS
from flask_sock import Sock

_BACKEND_ROOT = Path(__file__).resolve().parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_BACKEND_ROOT / ".env")
except ImportError:
    pass

from citywalk.bootstrap import configure_amap_keys

configure_amap_keys()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def _cors_origins() -> list:
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["*"]


def apply_cors(flask_app):
    CORS(
        flask_app,
        resources={
            r"/api/*": {
                "origins": _cors_origins(),
                "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
                "supports_credentials": False,
            }
        },
    )


app = Flask(__name__)
apply_cors(app)
sock = Sock(app)


@app.route("/")
def index():
    """API 服务指引。"""
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


from citywalk.api import register_blueprints as register_citywalk  # noqa: E402
from parking.api import register_blueprints as register_parking  # noqa: E402
from citywalk.api.routes_config import bp as bp_config  # noqa: E402

register_citywalk(app)
register_parking(app, sock)
app.register_blueprint(bp_config, url_prefix="/api")


@app.route("/api/health")
def api_health():
    return jsonify({"ok": True, "services": ["citywalk", "parking"]})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
