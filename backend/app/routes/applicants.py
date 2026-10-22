from fastapi import APIRouter, HTTPException

from app.db import connect
from app.schemas import DecisionIn
from app.services.actions import lead_decision, recheck_applicant
from app.services.applications import applicant_detail

router = APIRouter(prefix="/api")


@router.get("/applicants/{applicant_id}")
def get_applicant(applicant_id: str):
    with connect() as conn:
        detail = applicant_detail(conn, applicant_id)
    if not detail:
        raise HTTPException(404, "Applicant not found")
    return detail


@router.post("/applicants/{applicant_id}/decision")
def decide(applicant_id: str, body: DecisionIn):
    try:
        result = lead_decision(applicant_id, body)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if result is None:
        raise HTTPException(404, "Applicant not found")
    return result


@router.post("/applicants/{applicant_id}/recheck")
async def recheck(applicant_id: str):
    try:
        result = await recheck_applicant(applicant_id)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if result is None:
        raise HTTPException(404, "Applicant not found")
    return result


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: str):
    with connect() as conn:
        changed = conn.execute(
            "update notifications set read=true where id=%s returning id", (notification_id,)
        ).fetchone()
    if not changed:
        raise HTTPException(404, "Notification not found")
    return {"ok": True}
