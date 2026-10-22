from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db import connect
from app.schemas import LeadQuestionIn, StatusReplyIn
from app.services.status import get_status, save_reply

router = APIRouter(prefix="/api")


@router.get("/status/{token}")
def status_page(token: str):
    with connect() as conn:
        result = get_status(conn, token)
    if result is None:
        raise HTTPException(404, "Status token not found")
    return result


@router.post("/status/{token}/reply")
def reply_to_question(token: str, body: StatusReplyIn):
    with connect() as conn:
        result = save_reply(conn, token, body.text)
    if result is None:
        raise HTTPException(404, "Status token not found")
    return result


@router.post("/applicants/{applicant_id}/question")
def ask_applicant(applicant_id: str, body: LeadQuestionIn):
    try:
        applicant_uuid = UUID(applicant_id)
    except ValueError:
        raise HTTPException(404, "Applicant not found") from None
    with connect() as conn:
        updated = conn.execute(
            "update applicants set lead_question=%s where id=%s returning lead_question",
            (body.question, applicant_uuid),
        ).fetchone()
    if updated is None:
        raise HTTPException(404, "Applicant not found")
    return {"ok": True, "lead_question": updated["lead_question"]}
