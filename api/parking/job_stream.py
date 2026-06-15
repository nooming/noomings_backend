# -*- coding: utf-8 -*-
import json
import time

from parking.storage import db


def register_job_stream(sock):
    @sock.route("/api/parking/jobs/<job_id>/stream")
    def job_stream(ws, job_id):
        while True:
            job = db.get_job(job_id)
            if not job:
                ws.send(json.dumps({"status": "missing"}))
                return
            payload = {"status": job.get("status"), "progress": job.get("progress")}
            status = job.get("status")
            if status == "completed":
                payload["result"] = job.get("result")
                ws.send(json.dumps(payload))
                return
            if status == "failed":
                payload["error"] = job.get("error")
                ws.send(json.dumps(payload))
                return
            ws.send(json.dumps(payload))
            time.sleep(0.25)
