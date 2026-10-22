from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import connect
from app.routes import applicants, communities, demo, extras, misc

scheduler = BackgroundScheduler()


def _daily_recheck() -> None:
    from app.services.actions import recheck_applicant

    with connect() as conn:
        ids = conn.execute(
            """select id from applicants where status in ('declined','waitlisted')
            and decline_reason in ('skill_gap','minor_issue','capacity')
            and reconsider_after<=now()"""
        ).fetchall()
    for row in ids:
        try:
            asyncio.run(recheck_applicant(str(row["id"])))
        except Exception:
            continue


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("DISABLE_SCHEDULER") != "1":
        scheduler.add_job(_daily_recheck, "cron", hour=6, minute=0, id="daily-recheck", replace_existing=True)
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Gatekeeper API", version="1.0.0", lifespan=lifespan)
origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(communities.router)
app.include_router(applicants.router)
app.include_router(demo.router)
app.include_router(extras.router)
app.include_router(misc.router)
