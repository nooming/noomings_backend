# -*- coding: utf-8 -*-
from api.routes_plan import bp as bp_plan
from api.routes_agent import bp as bp_agent
from api.routes_media import bp as bp_media


def register_blueprints(app):
    app.register_blueprint(bp_plan)
    app.register_blueprint(bp_agent)
    app.register_blueprint(bp_media)
