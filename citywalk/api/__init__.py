# -*- coding: utf-8 -*-
"""Citywalk HTTP 路由注册。"""

_CITYWALK_PREFIX = "/api/citywalk"


def register_blueprints(app):
    from citywalk.api.routes_plan import bp as bp_plan
    from citywalk.api.routes_agent import bp as bp_agent
    from citywalk.api.routes_media import bp as bp_media

    app.register_blueprint(bp_plan, url_prefix=_CITYWALK_PREFIX)
    app.register_blueprint(bp_agent, url_prefix=_CITYWALK_PREFIX)
    app.register_blueprint(bp_media, url_prefix=_CITYWALK_PREFIX)
