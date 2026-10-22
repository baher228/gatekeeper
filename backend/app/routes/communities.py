from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from psycopg.types.json import Jsonb

from app.db import as_community, connect
from app.schemas import ApplyIn, SettingsIn
from app.services.applications import (
    apply_application,
    category_quotas,
    community_by_slug,
    summary,
)
from app.services.actions import recheck_applicant
from app.services.extras import identity_hashes

router = APIRouter(prefix="/api")


def _community(conn, row):
    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "name": row["name"],
        "description": row["description"],
        "rules": row["rules"],
        "reconsider_cooldown_days": row["reconsider_cooldown_days"],
        "categories": category_quotas(conn, row["id"]),
    }


@router.get("/communities")
def list_communities():
    with connect() as conn:
        rows = conn.execute("select id,slug,name from communities order by name").fetchall()
        return [{"id": str(row["id"]), "slug": row["slug"], "name": row["name"]} for row in rows]


@router.get("/communities/{slug}")
def get_community(slug: str):
    with connect() as conn:
        row = community_by_slug(conn, slug)
        if not row:
            raise HTTPException(404, "Community not found")
        return _community(conn, row)


@router.put("/communities/{slug}/settings")
def update_settings(slug: str, body: SettingsIn):
    with connect() as conn:
        row = community_by_slug(conn, slug)
        if not row:
            raise HTTPException(404, "Community not found")
        rules = [
            {"id": rule.id or f"rule-{index + 1}", "text": rule.text}
            for index, rule in enumerate(body.rules)
        ]
        conn.execute(
            "update communities set rules=%s,reconsider_cooldown_days=%s where id=%s",
            (Jsonb(rules), body.reconsider_cooldown_days, row["id"]),
        )
        conn.execute("delete from categories where community_id=%s", (row["id"],))
        for category in body.categories:
            conn.execute(
                "insert into categories(community_id,slug,name,quota,bypass_quota) values (%s,%s,%s,%s,%s)",
                (row["id"], category.slug, category.name, category.quota, category.bypass_quota),
            )
        row = community_by_slug(conn, slug)
        return _community(conn, row)


@router.post("/communities/{slug}/apply")
async def apply(slug: str, body: ApplyIn):
    try:
        result = await apply_application(slug, body.model_dump())
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    if result is None:
        raise HTTPException(404, "Community not found")
    return result


@router.get("/communities/{slug}/applicants")
def list_applicants(
    slug: str,
    status: str | None = None,
    category: str | None = None,
    q: str | None = None,
    liked: bool = False,
    returning: bool = False,
):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        sql = "select * from applicants where community_id=%s"
        params: list[object] = [community["id"]]
        if status:
            sql += " and status=%s"
            params.append(status)
        if category:
            sql += " and category=%s"
            params.append(category)
        if q:
            sql += " and (name ilike %s or email ilike %s or what_build ilike %s)"
            params.extend([f"%{q}%"] * 3)
        sql += " order by created_at desc"
        rows = conn.execute(sql, params).fetchall()
        hashes_by_id = {row["id"]: identity_hashes(row) for row in rows}
        all_hashes = list(dict.fromkeys(
            digest for hashes in hashes_by_id.values() for digest in hashes
        ))
        attendance_by_hash: dict[str, dict[str, int]] = {}
        liked_hashes = set()
        if all_hashes:
            with as_community(conn, community["id"]):
                attendance_rows = conn.execute(
                    """select identity_hash,status,count(*) as n from attendance
                    where community_id=%s and identity_hash=any(%s)
                    group by identity_hash,status""",
                    (community["id"], all_hashes),
                ).fetchall()
                likes = conn.execute(
                    """select identity_hash from attendee_likes
                    where community_id=%s and identity_hash=any(%s)""",
                    (community["id"], all_hashes),
                ).fetchall()
            for activity in attendance_rows:
                attendance_by_hash.setdefault(activity["identity_hash"], {})[
                    activity["status"]
                ] = int(activity["n"])
            liked_hashes = {row["identity_hash"] for row in likes}

        results = []
        for row in rows:
            hashes = hashes_by_id[row["id"]]
            attended = sum(attendance_by_hash.get(digest, {}).get("attended", 0) for digest in hashes)
            no_show = sum(attendance_by_hash.get(digest, {}).get("no_show", 0) for digest in hashes)
            is_liked = any(digest in liked_hashes for digest in hashes)
            if (liked and not is_liked) or (returning and attended == 0):
                continue
            applicant = summary(row)
            applicant.update(attended=attended, no_show=no_show, liked=is_liked)
            results.append(applicant)
        return results


@router.get("/communities/{slug}/events")
def list_events(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        applicants = conn.execute(
            """select id,name,status,email,phone,github,chat_handle
            from applicants where community_id=%s""",
            (community["id"],),
        ).fetchall()
        hashes_by_id = {row["id"]: identity_hashes(row) for row in applicants}
        applicants_by_hash: dict[str, list[dict]] = {}
        for applicant in applicants:
            for digest in hashes_by_id[applicant["id"]]:
                applicants_by_hash.setdefault(digest, []).append(applicant)

        with as_community(conn, community["id"]):
            attendance_rows = conn.execute(
                """select identity_hash,event_name,event_date,status,created_at
                from attendance where community_id=%s
                order by event_date desc,event_name,created_at desc""",
                (community["id"],),
            ).fetchall()
            likes = conn.execute(
                "select identity_hash from attendee_likes where community_id=%s",
                (community["id"],),
            ).fetchall()
        liked_hashes = {row["identity_hash"] for row in likes}
        liked_by_applicant = {
            applicant_id: any(digest in liked_hashes for digest in hashes)
            for applicant_id, hashes in hashes_by_id.items()
        }
        groups: dict[tuple[str, object], dict] = {}
        seen_attendees: dict[tuple[str, object], set] = {}
        for attendance in attendance_rows:
            key = (attendance["event_name"], attendance["event_date"])
            group = groups.setdefault(
                key, {"attended": 0, "no_show": 0, "attendees": []}
            )
            group[attendance["status"]] += 1
            seen = seen_attendees.setdefault(key, set())
            for applicant in applicants_by_hash.get(attendance["identity_hash"], []):
                applicant_id = applicant["id"]
                if applicant_id in seen:
                    continue
                seen.add(applicant_id)
                group["attendees"].append(
                    {
                        "applicant_id": str(applicant_id),
                        "name": applicant["name"],
                        "status": attendance["status"],
                        "liked": liked_by_applicant[applicant_id],
                    }
                )
        return [
            {
                "event_name": event_name,
                "event_date": event_date.isoformat(),
                **groups[(event_name, event_date)],
            }
            for event_name, event_date in sorted(
                groups, key=lambda key: (key[1], key[0]), reverse=True
            )
        ]


@router.get("/communities/{slug}/queue")
def queue(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        rows = conn.execute(
            "select id from applicants where community_id=%s and status='ask' order by created_at",
            (community["id"],),
        ).fetchall()
        from app.services.applications import applicant_detail
        return [applicant_detail(conn, str(row["id"])) for row in rows]


@router.post("/communities/{slug}/recheck-due")
async def recheck_due(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        rows = conn.execute(
            """select id from applicants where community_id=%s
            and status in ('declined','waitlisted')
            and decline_reason in ('skill_gap','minor_issue','capacity')
            and reconsider_after<=now() order by reconsider_after""",
            (community["id"],),
        ).fetchall()
    changed = []
    for row in rows:
        try:
            detail = await recheck_applicant(str(row["id"]))
            if detail:
                changed.append({
                    "id": detail["id"], "name": detail["name"], "category": detail["category"],
                    "status": detail["status"], "final_score": detail["final_score"],
                    "confidence": detail["confidence"], "top_reason": detail["top_reason"],
                    "decision_source": detail["decision_source"], "created_at": detail["created_at"],
                    "is_seed": detail["is_seed"], "reconsidered": detail["reconsidered"],
                })
        except ValueError:
            continue
    return {"checked": len(rows), "changed": changed}


@router.get("/communities/{slug}/notifications")
def notifications(slug: str):
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            raise HTTPException(404, "Community not found")
        rows = conn.execute(
            """select n.*,a.name as applicant_name from notifications n
            left join applicants a on a.id=n.applicant_id where n.community_id=%s
            order by n.created_at desc""",
            (community["id"],),
        ).fetchall()
        return [
            {
                "id": str(row["id"]), "applicant_id": str(row["applicant_id"]) if row["applicant_id"] else None,
                "applicant_name": row["applicant_name"], "kind": row["kind"],
                "message": row["message"], "read": row["read"], "created_at": row["created_at"],
            }
            for row in rows
        ]
