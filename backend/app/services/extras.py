from __future__ import annotations

from app.db import as_community
from app.services.blocklist import identifier_hash


def _identifiers(applicant: dict) -> list[tuple[str, str]]:
    return [
        (kind, value)
        for kind, value in [
            ("phone", applicant.get("phone")),
            ("email", applicant.get("email")),
            ("github", applicant.get("github")),
            ("handle", applicant.get("chat_handle")),
        ]
        if value
    ]


def identity_hashes(applicant: dict) -> list[str]:
    return list(dict.fromkeys(
        identifier_hash(kind, value) for kind, value in _identifiers(applicant)
    ))


def primary_hash(applicant: dict) -> str | None:
    email = applicant.get("email")
    if email:
        return identifier_hash("email", email)
    hashes = identity_hashes(applicant)
    return hashes[0] if hashes else None


def _note(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "flag": row["flag"],
        "note": row["note"],
        "visibility": row["visibility"],
        "author": row["author"],
        "community_name": row["community_name"],
        "created_at": row["created_at"].isoformat(),
    }


def identity_extras(conn, community_id, applicant: dict) -> dict:
    empty = {
        "attendance": {"attended": 0, "no_show": 0, "events": []},
        "ban": None,
        "own_notes": [],
        "shared_notes": [],
        "shared_flags": [],
    }
    hashes = identity_hashes(applicant)
    if not hashes:
        return empty

    with as_community(conn, community_id):
        events = conn.execute(
            """select event_name,event_date,status from attendance
            where community_id=%s and identity_hash=any(%s)
            order by event_date desc,created_at desc""",
            (community_id, hashes),
        ).fetchall()
        ban = conn.execute(
            """select id,reason,created_at,label from community_bans
            where community_id=%s and identity_hash=any(%s)
            order by created_at desc limit 1""",
            (community_id, hashes),
        ).fetchone()
        own_rows = conn.execute(
            """select n.*,c.name as community_name from attendee_notes n
            join communities c on c.id=n.community_id
            where n.community_id=%s and n.identity_hash=any(%s)
            order by n.created_at desc""",
            (community_id, hashes),
        ).fetchall()
        shared_rows = conn.execute(
            """select n.*,c.name as community_name from attendee_notes n
            join communities c on c.id=n.community_id
            where n.community_id<>%s and n.visibility='shared'
            and n.identity_hash=any(%s) order by n.created_at desc""",
            (community_id, hashes),
        ).fetchall()

    own_notes = [_note(row) for row in own_rows]
    shared_notes = [_note(row) for row in shared_rows]
    shared_flags = []
    seen_flags = set()
    for note in shared_notes:
        key = (note["flag"], note["community_name"])
        if note["flag"] and key not in seen_flags:
            seen_flags.add(key)
            shared_flags.append({"flag": note["flag"], "community_name": note["community_name"]})
    return {
        "attendance": {
            "attended": sum(row["status"] == "attended" for row in events),
            "no_show": sum(row["status"] == "no_show" for row in events),
            "events": [
                {
                    "event_name": row["event_name"],
                    "event_date": row["event_date"].isoformat(),
                    "status": row["status"],
                }
                for row in events
            ],
        },
        "ban": {
            "id": str(ban["id"]),
            "reason": ban["reason"],
            "created_at": ban["created_at"].isoformat(),
            "label": ban["label"],
        } if ban else None,
        "own_notes": own_notes,
        "shared_notes": shared_notes,
        "shared_flags": shared_flags,
    }


def score_adjustment(attendance: dict) -> tuple[float, str | None]:
    attended = int(attendance.get("attended", 0))
    no_show = int(attendance.get("no_show", 0))
    adjustment = 0.0
    reasons = []
    if attended:
        adjustment += 0.05
        reasons.append(f"Attended {attended} of your past events")
    if no_show:
        adjustment -= min(0.05 * no_show, 0.15)
        reasons.append(f"No-show at {no_show} of your past events")
    return adjustment, "; ".join(reasons) if reasons else None
