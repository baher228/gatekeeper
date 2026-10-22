from __future__ import annotations

from datetime import datetime, timedelta, timezone
from psycopg.types.json import Jsonb

from app.db import connect
from app.schemas import DecisionIn
from app.seed import DEMO_FIXTURES
from app.services.applications import applicant_detail, category_quotas
from app.services.evidence import gather_evidence
from app.services.history import feature_vector, train_model
from app.services.rules import calculate_rule_score, check_rules
from app.services.router import route


async def _recheck_rule_checks(
    rules: list[dict],
    applicant: dict,
    evidence: dict,
    stored_recommendation: dict,
) -> tuple[list[dict], dict]:
    stored_llm = stored_recommendation.get("llm") or {}
    stored_checks = stored_recommendation.get("rule_checks") or []
    if stored_llm.get("status") in ("live", "cached") and stored_checks:
        return stored_checks, {
            "status": "cached",
            "provider": stored_llm.get("provider"),
            "model": stored_llm.get("model"),
            "error": None,
        }
    return await check_rules(rules, applicant, evidence, allow_llm=False)


def lead_decision(applicant_id: str, decision: DecisionIn) -> dict | None:
    if decision.verdict == "decline" and not decision.reason_category:
        raise ValueError("reason_category is required when declining")
    with connect() as conn:
        app_row = conn.execute(
            """select a.*,c.reconsider_cooldown_days from applicants a
            join communities c on c.id=a.community_id where a.id=%s""",
            (applicant_id,),
        ).fetchone()
        if not app_row:
            return None
        rec = app_row["recommendation"] or {}
        status = {"accept": "accepted", "ask_more": "ask", "decline": "declined"}[decision.verdict]
        category_info = conn.execute(
            "select * from categories where community_id=%s and slug=%s",
            (app_row["community_id"], app_row["category"]),
        ).fetchone()
        accepted = conn.execute(
            "select count(*) as n from applicants where community_id=%s and category=%s and status='accepted'",
            (app_row["community_id"], app_row["category"]),
        ).fetchone()["n"]
        over_quota = (
            decision.verdict == "accept"
            and not category_info["bypass_quota"]
            and accepted >= category_info["quota"]
        )
        if over_quota:
            rec.setdefault("reasons", []).insert(0, "Lead override: accepted despite category being over quota")
            rec.setdefault("quota", {})["over_quota"] = True
        rec["verdict"] = decision.verdict.replace("_more", "")
        if decision.note:
            rec.setdefault("reasons", []).insert(0, decision.note)
        rec["route_rule"] = "lead_decision"
        rec["decline_reason"] = decision.reason_category
        cooldown = app_row["reconsider_cooldown_days"]
        now = datetime.now(timezone.utc)
        reconsider_after = (
            now + timedelta(days=cooldown)
            if decision.verdict == "decline" and decision.reason_category in ("skill_gap", "minor_issue", "capacity")
            else None
        )
        previous_decline = None
        if decision.verdict == "decline":
            previous_decline = {
                "declined_at": now.isoformat(),
                "reason_category": decision.reason_category,
            }
        conn.execute(
            """update applicants set status=%s,decision_source='lead',recommendation=%s,
            decline_reason=%s,decided_at=%s,reconsider_after=%s,previous_decline=%s
            where id=%s""",
            (
                status, Jsonb(rec), decision.reason_category if status == "declined" else None,
                now, reconsider_after, Jsonb(previous_decline) if previous_decline else None,
                applicant_id,
            ),
        )
        conn.execute(
            """insert into decisions(applicant_id,community_id,verdict,reason_category,note,
            source,features,created_at,is_seed) values (%s,%s,%s,%s,%s,'lead',%s,%s,%s)""",
            (
                applicant_id, app_row["community_id"], decision.verdict,
                decision.reason_category, decision.note, Jsonb(app_row["features"] or {}), now,
                app_row["is_seed"],
            ),
        )
        if status == "ask":
            conn.execute(
                """insert into notifications(community_id,applicant_id,kind,message,is_seed)
                values (%s,%s,'needs_review',%s,%s)""",
                (app_row["community_id"], applicant_id, f"{app_row['name']} needs a lead review.", app_row["is_seed"]),
            )
        detail = applicant_detail(conn, applicant_id)
        community_id = str(app_row["community_id"])
    model = train_model(community_id)
    return {"applicant": detail, "model": model}


async def recheck_applicant(applicant_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """select a.*,c.slug as community_slug,c.rules,c.reconsider_cooldown_days
            from applicants a join communities c on c.id=a.community_id where a.id=%s""",
            (applicant_id,),
        ).fetchone()
        if not row:
            return None
        now = datetime.now(timezone.utc)
        if row["status"] not in ("declined", "waitlisted"):
            raise ValueError("Only declined or waitlisted applicants can be reconsidered.")
        if row["decline_reason"] == "scam_abuse":
            raise ValueError("Scam/abuse decisions are not eligible for reconsideration.")
        if row["decline_reason"] not in ("skill_gap", "minor_issue", "capacity"):
            raise ValueError("This decline reason is not eligible for reconsideration.")
        if not row["reconsider_after"] or now < row["reconsider_after"]:
            date = row["reconsider_after"].isoformat() if row["reconsider_after"] else "not set"
            raise ValueError(f"Reconsideration is available after {date}.")
        old_rec = row["recommendation"] or {}
        old_evidence = old_rec.get("evidence", {})
        old_gh = old_evidence.get("github", {})
        handle = row["chat_handle"] or row["github"] or ""
        fixture = DEMO_FIXTURES.get(handle.strip().lstrip("@"))
        current_fixture = fixture.get("evidence_now") if fixture and fixture.get("evidence_now") else fixture
        applicant = {
            "name": row["name"], "email": row["email"], "phone": row["phone"],
            "github": row["github"], "devpost": row["devpost"], "chat_handle": row["chat_handle"],
            "what_build": row["what_build"], "category": row["category"],
        }
        evidence = await gather_evidence(applicant, current_fixture)
        cats = category_quotas(conn, row["community_id"])
        category = next((cat for cat in cats if cat["slug"] == row["category"]), None)
        matches = old_evidence.get("blocklist", {}).get("matches", [])
        checks, llm = await _recheck_rule_checks(
            row["rules"], applicant, evidence, old_rec
        )
        rule_score = calculate_rule_score(checks, evidence, row["category"])
        feature_categories = [cat["slug"] for cat in cats]
        vector = feature_vector(applicant, {"rule_score": rule_score, "rule_checks": checks}, evidence, feature_categories)
        from app.services.history import predict
        history = predict(str(row["community_id"]), vector, feature_categories)
        routed = route(
            applicant, checks, rule_score, evidence, history, category or {},
            matches, row["reconsider_cooldown_days"],
        )
        rec = routed["recommendation"]
        rec["llm"] = llm
        new_gh = evidence.get("github", {})
        delta = []
        if new_gh.get("public_repos") is not None:
            old_repos = old_gh.get("public_repos", 0) or 0
            delta.append(f"GitHub {new_gh['public_repos']} repos (was {old_repos})")
        new_dp = evidence.get("devpost", {})
        if new_dp.get("wins"):
            delta.append(f"{new_dp['wins']} Devpost win" + ("s" if new_dp["wins"] != 1 else ""))
        declined_at = (row["previous_decline"] or {}).get("declined_at") or row["decided_at"].date().isoformat()
        prior_reason = row["decline_reason"]
        note = f"Previously declined on {str(declined_at)[:10]} for {prior_reason}; now " + (", ".join(delta) or "evidence rechecked")
        status = routed["status"]
        reason = routed["decline_reason"]
        next_reconsider = None
        previous = dict(row["previous_decline"] or {})
        previous["note"] = note
        previous["declined_at"] = str(declined_at)
        previous["reason_category"] = prior_reason
        if status == "declined":
            # A continued eligible decline starts a fresh cooldown.
            reason = reason or prior_reason
            status = "declined"
            next_reconsider = now + timedelta(days=row["reconsider_cooldown_days"])
        elif status == "waitlisted":
            reason = "capacity"
            next_reconsider = now + timedelta(days=row["reconsider_cooldown_days"])
        else:
            reason = None
        conn.execute(
            """update applicants set status=%s,decision_source='auto',final_score=%s,confidence=%s,
            recommendation=%s,features=%s,decline_reason=%s,decided_at=%s,reconsider_after=%s,
            previous_decline=%s,reconsidered=true where id=%s""",
            (
                status, rec["final_score"], rec["confidence"], Jsonb(rec), Jsonb(vector), reason,
                now, next_reconsider, Jsonb(previous), applicant_id,
            ),
        )
        conn.execute(
            """insert into notifications(community_id,applicant_id,kind,message,is_seed)
            values (%s,%s,'reconsidered',%s,%s)""",
            (row["community_id"], applicant_id, note, row["is_seed"]),
        )
        if status == "ask":
            conn.execute(
                """insert into notifications(community_id,applicant_id,kind,message,is_seed)
                values (%s,%s,'needs_review',%s,%s)""",
                (row["community_id"], applicant_id, f"{row['name']} needs a lead review after reconsideration.", row["is_seed"]),
            )
        return applicant_detail(conn, applicant_id)
