from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from psycopg.types.json import Jsonb

from app.db import as_community, connect
from app.services.blocklist import identifier_hash
from app.services.evidence import gather_evidence
from app.services.history import feature_vector, predict
from app.services.rules import calculate_rule_score, check_rules
from app.services.router import route
from app.seed import DEMO_FIXTURES


def community_by_slug(conn, slug: str):
    row = conn.execute("select * from communities where slug=%s", (slug,)).fetchone()
    return row


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


def _lookup_blocklist(conn, community_id: str, applicant: dict) -> list[dict]:
    hashes = {
        (kind, identifier_hash(kind, value))
        for kind, value in _identifiers(applicant)
    }
    if not hashes:
        return []
    matched = []
    with as_community(conn, community_id):
        for kind, digest in hashes:
            rows = conn.execute(
                """select b.*, c.slug as community_slug,c.name as community_name
                from blocklist_entries b join communities c on c.id=b.reporting_community_id
                where b.identifier_hash=%s""",
                (digest,),
            ).fetchall()
            matched.extend(
                {
                    "entry_id": str(row["id"]),
                    "identifier_type": row["identifier_type"],
                    "status": row["status"],
                    "reporting_community": row["community_name"],
                    "reporting_community_slug": row["community_slug"],
                    "evidence": row["evidence"],
                    "links": row["links"],
                    "reported_at": row["created_at"].isoformat(),
                }
                for row in rows
            )
    return matched


async def apply_application(slug: str, incoming: dict) -> dict | None:
    applicant = dict(incoming)
    handle = applicant.get("chat_handle") or applicant.get("github") or ""
    fixture = DEMO_FIXTURES.get(handle.strip().lstrip("@"))
    evidence = await gather_evidence(applicant, fixture)
    with connect() as conn:
        community = community_by_slug(conn, slug)
        if not community:
            return None
        category = conn.execute(
            "select * from categories where community_id=%s and slug=%s",
            (community["id"], applicant["category"]),
        ).fetchone()
        if not category:
            raise ValueError("Unknown category for this community")
        matches = _lookup_blocklist(conn, community["id"], applicant)
        used = conn.execute(
            "select count(*) as n from applicants where community_id=%s and category=%s and status='accepted'",
            (community["id"], category["slug"]),
        ).fetchone()["n"]
        waiting = conn.execute(
            "select count(*) as n from applicants where community_id=%s and category=%s and status='waitlisted'",
            (community["id"], category["slug"]),
        ).fetchone()["n"]
        quota = {
            "slug": category["slug"], "quota": category["quota"], "used": used,
            "remaining": max(0, category["quota"] - used), "waitlisted": waiting,
            "bypass_quota": category["bypass_quota"],
        }
        checks, llm = await check_rules(community["rules"], applicant, evidence)
        rule_score = calculate_rule_score(checks, evidence, category["slug"])
        categories = [
            row["slug"] for row in conn.execute(
                "select slug from categories where community_id=%s order by slug", (community["id"],)
            ).fetchall()
        ]
        preliminary = {"rule_score": rule_score, "rule_checks": checks}
        features = feature_vector(applicant, preliminary, evidence, categories)
        history = predict(str(community["id"]), features, categories)
        result = route(
            applicant, checks, rule_score, evidence, history, quota, matches,
            community["reconsider_cooldown_days"],
        )
        recommendation = result["recommendation"]
        recommendation["llm"] = llm
        recommendation["evidence"]["blocklist"] = {"hit": bool(matches), "matches": matches}
        now = datetime.now(timezone.utc)
        if result["status"] == "waitlisted":
            rank = conn.execute(
                """select count(*) as n from applicants where community_id=%s and category=%s
                and status='waitlisted' and final_score >= %s""",
                (community["id"], category["slug"], recommendation["final_score"]),
            ).fetchone()["n"]
            recommendation["quota"]["waitlist_rank"] = rank + 1
        reason = result["decline_reason"]
        reconsider_after = None
        previous_decline = None
        if reason in ("skill_gap", "minor_issue", "capacity"):
            reconsider_after = now + timedelta(days=community["reconsider_cooldown_days"])
        if result["status"] == "waitlisted":
            previous_decline = {"reason_category": "capacity", "declined_at": now.isoformat()}
        aid = conn.execute(
            """insert into applicants
            (community_id,name,email,phone,github,devpost,chat_handle,what_build,category,status,
             decision_source,final_score,confidence,recommendation,features,decline_reason,decided_at,
             reconsider_after,previous_decline,is_seed)
            values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'auto',%s,%s,%s,%s,%s,%s,%s,%s,false)
            returning id""",
            (
                community["id"], applicant["name"], applicant["email"], applicant.get("phone"),
                applicant.get("github"), applicant.get("devpost"), applicant.get("chat_handle"),
                applicant["what_build"], applicant["category"], result["status"],
                recommendation["final_score"], recommendation["confidence"], Jsonb(recommendation),
                Jsonb(features), reason, now, reconsider_after,
                Jsonb(previous_decline) if previous_decline else None,
            ),
        ).fetchone()["id"]
        conn.execute(
            """insert into decisions(applicant_id,community_id,verdict,reason_category,note,source,features)
            values (%s,%s,%s,%s,%s,'auto',%s)""",
            (
                aid, community["id"], "ask_more" if recommendation["verdict"] == "ask" else recommendation["verdict"], reason,
                recommendation["reasons"][0] if recommendation["reasons"] else None,
                Jsonb(features),
            ),
        )
        if result["status"] == "ask":
            conn.execute(
                "insert into notifications(community_id,applicant_id,kind,message) values (%s,%s,'needs_review',%s)",
                (community["id"], aid, f"{applicant['name']} needs a lead review."),
            )
        if recommendation["route_rule"] == "blocklist_confirmed":
            conn.execute(
                "insert into notifications(community_id,applicant_id,kind,message) values (%s,%s,'blocklist_hit',%s)",
                (community["id"], aid, f"{applicant['name']} matched a confirmed blocklist report."),
            )
        return applicant_detail(conn, str(aid))


def applicant_detail(conn, applicant_id: str) -> dict | None:
    row = conn.execute(
        """select a.*,c.slug as community_slug from applicants a
        join communities c on c.id=a.community_id where a.id=%s""",
        (applicant_id,),
    ).fetchone()
    if not row:
        return None
    decisions = conn.execute(
        "select verdict,reason_category,note,source,created_at from decisions where applicant_id=%s order by created_at",
        (applicant_id,),
    ).fetchall()
    rec = row["recommendation"] or {}
    reconsider_after = row["reconsider_after"]
    decline_reason = row["decline_reason"]
    eligible_reason = decline_reason in ("skill_gap", "minor_issue", "capacity")
    eligible = bool(
        row["status"] in ("declined", "waitlisted")
        and eligible_reason
        and reconsider_after
        and datetime.now(timezone.utc) >= reconsider_after
    )
    previous = row["previous_decline"]
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "category": row["category"],
        "status": row["status"],
        "final_score": row["final_score"],
        "confidence": row["confidence"],
        "top_reason": (rec.get("reasons") or [""])[0],
        "decision_source": row["decision_source"],
        "created_at": row["created_at"],
        "is_seed": row["is_seed"],
        "reconsidered": row["reconsidered"],
        "community_slug": row["community_slug"],
        "email": row["email"],
        "phone_masked": _mask_phone(row["phone"]),
        "github": row["github"],
        "devpost": row["devpost"],
        "chat_handle": row["chat_handle"],
        "what_build": row["what_build"],
        "decided_at": row["decided_at"],
        "decline_reason": decline_reason,
        "recommendation": rec,
        "reconsideration": {
            "eligible": eligible,
            "reconsider_after": reconsider_after,
            "previous": {
                "declined_at": (previous or {}).get("declined_at"),
                "reason_category": (previous or {}).get("reason_category"),
            } if previous else None,
            "note": (previous or {}).get("note"),
        },
        "decisions": decisions,
    }


def _mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    return "••••" + digits[-4:] if len(digits) >= 4 else "••••"


def summary(row: dict) -> dict:
    rec = row.get("recommendation") or {}
    return {
        "id": str(row["id"]), "name": row["name"], "category": row["category"],
        "status": row["status"], "final_score": row["final_score"],
        "confidence": row["confidence"],
        "top_reason": (rec.get("reasons") or [""])[0],
        "decision_source": row["decision_source"], "created_at": row["created_at"],
        "is_seed": row["is_seed"], "reconsidered": row["reconsidered"],
    }


def category_quotas(conn, community_id: str) -> list[dict]:
    cats = conn.execute("select * from categories where community_id=%s order by slug", (community_id,)).fetchall()
    result = []
    for cat in cats:
        counts = conn.execute(
            """select count(*) filter(where status='accepted') as used,
            count(*) filter(where status='waitlisted') as waitlisted from applicants
            where community_id=%s and category=%s""",
            (community_id, cat["slug"]),
        ).fetchone()
        used = counts["used"]
        result.append({
            "slug": cat["slug"], "name": cat["name"], "quota": cat["quota"],
            "bypass_quota": cat["bypass_quota"], "used": used,
            "remaining": max(0, cat["quota"] - used), "waitlisted": counts["waitlisted"],
        })
    return result
