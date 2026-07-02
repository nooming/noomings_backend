# -*- coding: utf-8 -*-
"""Parking HTTP 路由注册。"""


def register_blueprints(app, sock=None):
    from parking.api.routes_scenario import bp as bp_scenario
    from parking.api.routes_optimize import bp as bp_optimize
    from parking.api.routes_simulate import bp as bp_simulate
    from parking.api.job_stream import register_job_stream
    from parking.core.storage.db import init_db

    prefix = "/api/parking"
    for bp in (bp_scenario, bp_optimize, bp_simulate):
        app.register_blueprint(bp, url_prefix=prefix)
    if sock is not None:
        register_job_stream(sock)
    init_db()
