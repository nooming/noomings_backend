# -*- coding: utf-8 -*-
"""HTTP 路由统一注册。"""
from flask import jsonify


def register_blueprints(app, sock=None):
    from api.citywalk import register_citywalk_blueprints
    from api.parking import register_parking_blueprints
    from api.routes_config import bp as bp_config

    register_citywalk_blueprints(app)
    register_parking_blueprints(app, sock)
    app.register_blueprint(bp_config, url_prefix="/api")

    @app.route("/api/health")
    def api_health():
        return jsonify({"ok": True, "services": ["citywalk", "parking"]})
