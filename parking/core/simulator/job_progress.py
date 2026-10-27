# -*- coding: utf-8 -*-
"""异步任务进度上报。"""


def make_db_progress_reporter(jid, db_module):
    if not jid:
        return None

    def report(phase, label, pct=None):
        payload = {"phase": phase, "label": label}
        if pct is not None:
            payload["pct"] = round(float(pct), 3)
        db_module.update_job_progress(jid, payload)

    return report
