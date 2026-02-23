from __future__ import annotations

from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import get_conn, init_db
from app.services import PipelineError, generate_ideas, run_job, update_settings, get_settings

app = FastAPI(title="Brainrot Automation Studio")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    scheduler.start()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    with get_conn() as conn:
        jobs = conn.execute("SELECT * FROM jobs ORDER BY datetime(schedule_at) ASC").fetchall()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "jobs": jobs,
            "settings": get_settings(),
            "ideas": [],
            "error": None,
        },
    )


@app.post("/settings")
async def save_settings(
    gemini_api_key: str = Form(""),
    veo_api_key: str = Form(""),
    youtube_access_token: str = Form(""),
    instagram_access_token: str = Form(""),
    youtube_channel_id: str = Form(""),
    instagram_account_id: str = Form(""),
):
    update_settings(
        {
            "gemini_api_key": gemini_api_key,
            "veo_api_key": veo_api_key,
            "youtube_access_token": youtube_access_token,
            "instagram_access_token": instagram_access_token,
            "youtube_channel_id": youtube_channel_id,
            "instagram_account_id": instagram_account_id,
        }
    )
    return RedirectResponse(url="/", status_code=303)


@app.post("/ideas", response_class=HTMLResponse)
async def ideas(request: Request, topic: str = Form(...), count: int = Form(8)):
    error = None
    generated: list[str] = []
    try:
        generated = await generate_ideas(topic, count)
    except Exception as exc:
        error = str(exc)

    with get_conn() as conn:
        jobs = conn.execute("SELECT * FROM jobs ORDER BY datetime(schedule_at) ASC").fetchall()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "jobs": jobs,
            "settings": get_settings(),
            "ideas": generated,
            "error": error,
        },
    )


@app.post("/schedule")
async def schedule(
    title: str = Form(...),
    niche: str = Form(...),
    tone: str = Form("chaotic"),
    prompt_extra: str = Form(""),
    first_run_at: str = Form(...),
    repeats: int = Form(1),
    interval_minutes: int = Form(180),
):
    base_time = datetime.fromisoformat(first_run_at)

    with get_conn() as conn:
        for i in range(max(repeats, 1)):
            schedule_at = base_time + timedelta(minutes=interval_minutes * i)
            cur = conn.execute(
                """
                INSERT INTO jobs(title, niche, tone, prompt_extra, schedule_at, status)
                VALUES(?, ?, ?, ?, ?, 'scheduled')
                """,
                (title, niche, tone, prompt_extra, schedule_at.isoformat()),
            )
            job_id = cur.lastrowid
            scheduler.add_job(run_job, "date", run_date=schedule_at, args=[job_id], id=f"job_{job_id}")

    return RedirectResponse(url="/", status_code=303)


@app.post("/run/{job_id}")
async def run_now(job_id: int):
    try:
        await run_job(job_id)
    except PipelineError:
        pass
    return RedirectResponse(url="/", status_code=303)
