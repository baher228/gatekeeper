from __future__ import annotations

import os
from urllib.parse import urlencode


MESSAGES = {
    "accepted": "You're in.",
    "ask": "A lead is reviewing your application.",
    "waitlisted": "You're on the waitlist.",
    "declined": "Not accepted this time.",
}


def get_status(conn, token: str) -> dict | None:
    row = conn.execute(
        """select a.*,c.name as community_name,c.slug as community_slug
        from applicants a join communities c on c.id=a.community_id
        where a.status_token=%s""",
        (token,),
    ).fetchone()
    if not row:
        return None

    waitlist_position = None
    if row["status"] == "waitlisted":
        ranked = conn.execute(
            """select position from (
                select id,row_number() over(order by final_score desc,created_at asc) as position
                from applicants where community_id=%s and category=%s and status='waitlisted'
            ) ordered where id=%s""",
            (row["community_id"], row["category"], row["id"]),
        ).fetchone()
        waitlist_position = int(ranked["position"]) if ranked else None

    invite_url = None
    if row["status"] == "accepted":
        params = {"name": row["name"]}
        if row["github"]:
            params["github"] = row["github"]
        params["builds"] = row["what_build"]
        params["from"] = "gatekeeper"
        base_url = (os.getenv("MEMBER_NETWORK_URL") or "http://localhost:5174").rstrip("/")
        invite_url = f"{base_url}/join?{urlencode(params)}"

    recommendation = row["recommendation"] or {}
    evidence = recommendation.get("evidence") or {}
    blocklist_hit = bool((evidence.get("blocklist") or {}).get("hit"))
    return {
        "name": row["name"],
        "community_name": row["community_name"],
        "community_slug": row["community_slug"],
        "category": row["category"],
        "decision": row["status"],
        "waitlist_position": waitlist_position,
        "lead_question": row["lead_question"],
        "applicant_reply": row["applicant_reply"],
        "applicant_reply_at": (
            row["applicant_reply_at"].isoformat() if row["applicant_reply_at"] else None
        ),
        "message": MESSAGES[row["status"]],
        "invite_url": invite_url,
        "appeal_url": "/appeal" if row["status"] == "declined" and blocklist_hit else None,
    }


def save_reply(conn, token: str, text: str) -> dict | None:
    updated = conn.execute(
        """update applicants set applicant_reply=%s,applicant_reply_at=now()
        where status_token=%s returning id""",
        (text, token),
    ).fetchone()
    return get_status(conn, token) if updated else None
