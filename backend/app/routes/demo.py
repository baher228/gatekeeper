from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException
from starlette.concurrency import run_in_threadpool

from app.db import connect
from app.seed import seed

router = APIRouter(prefix="/api")


@router.post("/demo/reset")
async def reset_demo():
    if os.getenv("DEMO_RESET") == "0":
        raise HTTPException(403, "Demo reset is disabled")

    await run_in_threadpool(seed, if_empty=False)
    with connect() as conn:
        applicants = conn.execute(
            "select count(*) as n from applicants where is_seed=true"
        ).fetchone()["n"]
        queue = conn.execute(
            """select count(*) as n from applicants a
            join communities c on c.id=a.community_id
            where c.slug='grok-night-london' and a.status='ask'"""
        ).fetchone()["n"]
    return {"ok": True, "applicants": applicants, "queue": queue}
