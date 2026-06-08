"""FastAPI application: serves the UI and the pipeline API."""
import uuid
import threading
import pathlib

from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

import config
import pipeline

app = FastAPI(title="IT Outsourcing Lead Pipeline")


def require_auth(x_app_password: str = Header(default="")):
    """If APP_PASSWORD is set, require it on protected endpoints."""
    if config.APP_PASSWORD and x_app_password != config.APP_PASSWORD:
        raise HTTPException(401, "Unauthorized — wrong or missing password.")

FRONTEND = pathlib.Path(__file__).resolve().parent.parent / "frontend"

JOBS = {}  # in-memory store; fine for single-user local use


class RunParams(BaseModel):
    queries: List[str]
    platforms: List[str] = []
    country: str = "United States"
    remote: bool = True
    max_hours: int = config.DEFAULT_MAX_HOURS
    min_employees: int = config.DEFAULT_MIN_EMPLOYEES
    max_employees: int = config.DEFAULT_MAX_EMPLOYEES
    enrich_people: bool = False
    enrich_web: bool = False
    drop_staffing: bool = True


@app.get("/api/config")
def get_config():
    if config.FORCE_MOCK:
        mode_label, badge = "MOCK MODE", "mock"
    elif not config.SERPAPI_MOCK and config.APOLLO_ENABLED:
        mode_label, badge = "LIVE", "live"
    elif not config.SERPAPI_MOCK:
        mode_label, badge = "LIVE · Apollo off", "live"
    else:
        mode_label, badge = "MOCK MODE", "mock"
    return {
        "mock_mode": config.MOCK_MODE,
        "serpapi_live": not config.SERPAPI_MOCK,
        "apollo_live": config.APOLLO_ENABLED,
        "mode_label": mode_label,
        "badge": badge,
        "auth_required": bool(config.APP_PASSWORD),
        "default_queries": config.DEFAULT_ROLE_QUERIES,
        "countries": list(config.COUNTRY_OPTIONS.keys()),
        "defaults": {
            "max_hours": config.DEFAULT_MAX_HOURS,
            "min_employees": config.DEFAULT_MIN_EMPLOYEES,
            "max_employees": config.DEFAULT_MAX_EMPLOYEES,
        },
    }


@app.post("/api/run")
def run(params: RunParams, x_app_password: str = Header(default="")):
    require_auth(x_app_password)
    if not params.queries:
        raise HTTPException(400, "At least one role query is required.")
    job_id = uuid.uuid4().hex[:12]
    JOBS[job_id] = {"status": "queued", "stage": "queued", "log": [],
                    "rows": [], "counts": {}, "result_path": None}
    t = threading.Thread(target=pipeline.run_pipeline,
                         args=(JOBS[job_id], params.dict()), daemon=True)
    t.start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, x_app_password: str = Header(default="")):
    require_auth(x_app_password)
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    return {
        "status": job["status"],
        "stage": job["stage"],
        "log": job["log"],
        "rows": job["rows"],
        "counts": job["counts"],
        "result_name": job.get("result_name"),
        "download": f"/api/download/{job_id}" if job.get("result_path") else None,
    }


@app.get("/api/download/{job_id}")
def download(job_id: str, pw: str = ""):
    if config.APP_PASSWORD and pw != config.APP_PASSWORD:
        raise HTTPException(401, "Unauthorized.")
    job = JOBS.get(job_id)
    if not job or not job.get("result_path"):
        raise HTTPException(404, "No file for this job.")
    return FileResponse(
        job["result_path"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=job.get("result_name", "prospects.xlsx"),
    )


@app.get("/")
def index():
    return FileResponse(str(FRONTEND / "index.html"))


# Serve any other static assets if added later.
app.mount("/static", StaticFiles(directory=str(FRONTEND)), name="static")
