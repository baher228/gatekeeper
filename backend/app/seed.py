from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from app.db import connect, migrate
from app.services.blocklist import identifier_hash
from app.services.history import feature_vector, predict, train_model
from app.services.rules import calculate_rule_score, heuristic_checks
from app.services.router import route
from app.synthetic import SEED_KIND_COUNTS, lead_label, make_applicant
from psycopg.types.json import Jsonb

CATEGORIES = [
    ("builder", "Shipped builders", 35, False),
    ("researcher", "Researchers", 12, False),
    ("first_timer", "First-timers", 15, False),
    ("mentor", "Mentors & speakers", 8, False),
    ("vip", "VIP / partners", 10, True),
]

RULES_A = [
    {"id": "ship", "text": "Has shipped a real project, product, demo, or useful prototype"},
    {"id": "curious", "text": "Is curious, generous, and keen to learn from other builders"},
    {"id": "london", "text": "Based in or regularly building with the London community"},
    {"id": "contribute", "text": "Will share progress and contribute useful feedback"},
    {"id": "spam", "text": "No recruiting, selling, crypto pumping, or unsolicited promotion"},
]
RULES_B = [
    {"id": "ship", "text": "Has shipped something real (repo, demo, product, paper)"},
    {"id": "ai", "text": "Builds with AI/LLMs or wants to start"},
    {"id": "london", "text": "Based in or regularly in London"},
    {"id": "contribute", "text": "Will contribute: demo, help others, give feedback"},
    {"id": "spam", "text": "No recruiting/selling spam, no crypto pumping"},
]

DEMO_FIXTURES = {
    "demo-crypto-dave": {
        "github": {"status": "simulated", "login": "demo-crypto-dave", "account_age_days": 8, "public_repos": 1, "followers": 2, "recent_push_days": 1},
        "devpost": {"status": "simulated", "projects": 0, "wins": 0, "sample": []},
        "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
    },
    "demo-ada-ships": {
        "github": {"status": "simulated", "login": "demo-ada-ships", "account_age_days": 2100, "public_repos": 18, "followers": 52, "recent_push_days": 3},
        "devpost": {"status": "simulated", "projects": 3, "wins": 1, "sample": [{"name": "Civic Lens", "url": "https://example.com/civic-lens"}]},
        "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
    },
    "demo-sam-research": {
        "github": {"status": "simulated", "login": "demo-sam-research", "account_age_days": 180, "public_repos": 1, "followers": 8, "recent_push_days": 22},
        "devpost": {"status": "simulated", "projects": 1, "wins": 0, "sample": []},
        "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
    },
    "demo-maya-learns": {
        "github": {"status": "simulated", "login": "demo-maya-learns", "account_age_days": 90, "public_repos": 1, "followers": 1, "recent_push_days": 70},
        "devpost": {"status": "simulated", "projects": 0, "wins": 0, "sample": []},
        "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
    },
    "demo-ravi-prototype": {
        "github": {"status": "simulated", "login": "demo-ravi-prototype", "account_age_days": 80, "public_repos": 0, "followers": 0, "recent_push_days": None},
        "devpost": {"status": "simulated", "projects": 0, "wins": 0, "sample": []},
        "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
        "evidence_now": {"github": {"status": "simulated", "login": "demo-ravi-prototype", "account_age_days": 330, "public_repos": 9, "followers": 6, "recent_push_days": 4}, "devpost": {"status": "simulated", "projects": 1, "wins": 1, "sample": []}, "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0}},
    },
    "demo-jo-community": {
        "github": {"status": "simulated", "login": "demo-jo-community", "account_age_days": 120, "public_repos": 1, "followers": 2, "recent_push_days": 65},
        "devpost": {"status": "simulated", "projects": 0, "wins": 0, "sample": []},
        "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
        "evidence_now": {"github": {"status": "simulated", "login": "demo-jo-community", "account_age_days": 600, "public_repos": 11, "followers": 25, "recent_push_days": 3}, "devpost": {"status": "simulated", "projects": 2, "wins": 1, "sample": []}, "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0}},
    },
    "demo-old-scam-example": {
        "github": {"status": "simulated", "login": "demo-old-scam-example", "account_age_days": 12, "public_repos": 1, "followers": 1, "recent_push_days": 20},
        "devpost": {"status": "simulated", "projects": 0, "wins": 0, "sample": []},
        "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
    },
}
DEMO_FIXTURES["demo-maya-learns"]["evidence_now"] = {
    "github": {"status": "simulated", "login": "demo-maya-learns", "account_age_days": 320, "public_repos": 14, "followers": 14, "recent_push_days": 2},
    "devpost": {"status": "simulated", "projects": 2, "wins": 1, "sample": [{"name": "Quiet Hours", "url": "https://example.com/quiet-hours"}]},
    "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
}


def _insert_applicant(conn, community_id, *, name, email, category, status, what_build,
                      created_at, recommendation, github=None, devpost=None, phone=None,
                      chat_handle=None, decline_reason=None, decided_at=None,
                      reconsider_after=None, previous_decline=None, features=None,
                      decision_source="lead", is_seed=True):
    row = conn.execute(
        """insert into applicants
        (community_id,name,email,phone,github,devpost,chat_handle,what_build,category,status,
         decision_source,final_score,confidence,recommendation,features,decline_reason,decided_at,
         reconsider_after,previous_decline,created_at,is_seed)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        returning id""",
        (community_id, name, email, phone, github, devpost, chat_handle, what_build, category,
         status, decision_source, recommendation.get("final_score", 0.5),
         recommendation.get("confidence", 0.5), Jsonb(recommendation), Jsonb(features or {}),
         decline_reason, decided_at, reconsider_after,
         Jsonb(previous_decline) if previous_decline else None,
         created_at, is_seed),
    ).fetchone()
    return row["id"]


def _quota(conn, community_id, category_slug):
    category = conn.execute(
        "select * from categories where community_id=%s and slug=%s",
        (community_id, category_slug),
    ).fetchone()
    counts = conn.execute(
        """select count(*) filter(where status='accepted') as used,
        count(*) filter(where status='waitlisted') as waitlisted from applicants
        where community_id=%s and category=%s""",
        (community_id, category_slug),
    ).fetchone()
    return {
        "slug": category_slug,
        "quota": category["quota"],
        "used": counts["used"],
        "remaining": max(0, category["quota"] - counts["used"]),
        "waitlisted": counts["waitlisted"],
        "bypass_quota": category["bypass_quota"],
    }


def _score_applicant(applicant, evidence, categories, quota, community_id, use_history=False):
    checks = heuristic_checks(RULES_B, applicant, evidence)
    rule_score = calculate_rule_score(checks, evidence, applicant["category"])
    features = feature_vector(
        applicant,
        {"rule_score": rule_score, "rule_checks": checks},
        evidence,
        categories,
    )
    history = predict(community_id, features, categories) if use_history else {
        "available": False,
        "p_accept": None,
        "n_training": 0,
        "top_features": [],
    }
    result = route(applicant, checks, rule_score, evidence, history, quota, [])
    result["recommendation"]["llm"] = {
        "status": "unavailable",
        "provider": None,
        "model": None,
        "error": "seed data – scored with heuristic rules",
    }
    return result, features


def seed(*, if_empty=False) -> None:
    migrate()
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    with connect() as conn:
        found = conn.execute("select count(*) as n from communities").fetchone()["n"]
        if if_empty and found:
            return
        for slug in ("shoreditch-builders", "grok-night-london"):
            existing = conn.execute(
                "select is_seed from communities where slug=%s", (slug,)
            ).fetchone()
            if existing and not existing["is_seed"]:
                raise RuntimeError(f"Refusing to reset non-seed community {slug}")
        conn.execute(
            """update applicants set is_seed=true where is_seed=false and (
            lower(ltrim(btrim(coalesce(github,'')), '@')) like 'demo-%' or
            lower(ltrim(btrim(coalesce(devpost,'')), '@')) like 'demo-%' or
            lower(ltrim(btrim(coalesce(chat_handle,'')), '@')) like 'demo-%')"""
        )
        conn.execute(
            """update decisions set is_seed=true where is_seed=false
            and applicant_id in (select id from applicants where is_seed=true)"""
        )
        conn.execute(
            """update notifications set is_seed=true where is_seed=false and applicant_id in
            (select id from applicants where is_seed=true)"""
        )
        conn.execute(
            """delete from blocklist_entries as b where b.is_seed
            and not exists (select 1 from appeals as a where a.entry_id=b.id)"""
        )
        conn.execute("delete from notifications where is_seed")
        conn.execute("delete from decisions where is_seed")
        conn.execute("delete from applicants where is_seed")
        communities = {}
        for slug, name, description, rules in [
            ("shoreditch-builders", "Shoreditch Builders Club", "A friendly home for people shipping useful things in East London.", RULES_A),
            ("grok-night-london", "Grok Night London", "London builders exploring practical AI and sharing what they learn.", RULES_B),
        ]:
            row = conn.execute(
                """insert into communities(slug,name,description,rules,reconsider_cooldown_days,is_seed)
                values (%s,%s,%s,%s,60,true) on conflict(slug) do update set
                name=excluded.name, description=excluded.description, rules=excluded.rules,
                reconsider_cooldown_days=60, is_seed=true
                where communities.is_seed=true returning id""",
                (slug, name, description, Jsonb(rules)),
            ).fetchone()
            if not row:
                raise RuntimeError(f"Refusing to reset non-seed community {slug}")
            communities[slug] = row["id"]
        community_ids = communities
        for slug, cid in community_ids.items():
            for cat_slug, cat_name, quota, bypass in CATEGORIES:
                conn.execute(
                    """insert into categories(community_id,slug,name,quota,bypass_quota)
                    values (%s,%s,%s,%s,%s) on conflict (community_id,slug) do update set
                    name=excluded.name, quota=excluded.quota, bypass_quota=excluded.bypass_quota""",
                    (cid, cat_slug, cat_name, quota, bypass),
                )

        b_id = community_ids["grok-night-london"]
        categories = [category[0] for category in CATEGORIES]
        accepted_limits = {
            slug: max(0, quota - 3)
            for slug, _, quota, _ in CATEGORIES
        }
        accepted_counts = {
            slug: conn.execute(
                "select count(*) as n from applicants where community_id=%s and category=%s and status='accepted'",
                (b_id, slug),
            ).fetchone()["n"]
            for slug, _, _, _ in CATEGORIES
        }
        kinds = tuple(SEED_KIND_COUNTS)
        weights = tuple(SEED_KIND_COUNTS.values())
        history_count = 0
        attempts = 0
        while history_count < 120:
            attempts += 1
            if attempts > 1000:
                raise RuntimeError("Could not fill the 120-row seed history within quota caps")
            kind = rng.choices(kinds, weights=weights, k=1)[0]
            applicant = make_applicant(rng, kind)
            verdict = lead_label(applicant, rng)
            category = applicant["category"]
            if verdict == "accept" and accepted_counts[category] >= accepted_limits[category]:
                continue
            created = now - timedelta(days=rng.randint(31, 119), minutes=rng.randrange(1440))
            quota = _quota(conn, b_id, category)
            result, features = _score_applicant(
                applicant, applicant["evidence"], categories, quota, str(b_id)
            )
            status = "accepted" if verdict == "accept" else "declined"
            reason = None if verdict == "accept" else (
                "scam_abuse" if kind == "scammer"
                else "rules_mismatch" if kind == "recruiter_seller"
                else "skill_gap"
            )
            aid = _insert_applicant(
                conn, b_id, name=applicant["name"], email=applicant["email"],
                phone=applicant["phone"], github=applicant["github"],
                devpost=applicant["devpost"], chat_handle=applicant["chat_handle"],
                category=category, status=status, what_build=applicant["what_build"],
                created_at=created, decided_at=created, recommendation=result["recommendation"],
                features=features, decline_reason=reason, decision_source="lead",
            )
            conn.execute(
                """insert into decisions
                (applicant_id,community_id,verdict,reason_category,note,source,features,created_at,is_seed)
                values (%s,%s,%s,%s,%s,'seed',%s,%s,true)""",
                (
                    aid, b_id, verdict, reason, f"Synthetic lead label: {kind}",
                    Jsonb(features), created,
                ),
            )
            accepted_counts[category] += int(verdict == "accept")
            history_count += 1

        conn.commit()
        model_info = train_model(str(b_id), seed_only=True)
        if not model_info["available"]:
            raise RuntimeError("The synthetic seed history did not produce a trainable model")

        queue_rng = random.Random(7)
        queue_count = 0
        queue_attempts = 0
        while queue_count < 6:
            queue_attempts += 1
            if queue_attempts > 300:
                raise RuntimeError("Could not find six routed ask applicants within 300 attempts")
            kind = queue_rng.choices(kinds, weights=weights, k=1)[0]
            applicant = make_applicant(queue_rng, kind)
            quota = _quota(conn, b_id, applicant["category"])
            result, features = _score_applicant(
                applicant, applicant["evidence"], categories, quota, str(b_id), use_history=True
            )
            if result["status"] != "ask":
                continue
            created = now - timedelta(hours=6 - queue_count, minutes=queue_rng.randrange(60))
            aid = _insert_applicant(
                conn, b_id, name=applicant["name"], email=applicant["email"],
                phone=applicant["phone"], github=applicant["github"],
                devpost=applicant["devpost"], chat_handle=applicant["chat_handle"],
                category=applicant["category"], status="ask",
                what_build=applicant["what_build"], created_at=created,
                recommendation=result["recommendation"], features=features,
                decision_source="auto",
            )
            conn.execute(
                """insert into decisions
                (applicant_id,community_id,verdict,note,source,features,created_at,is_seed)
                values (%s,%s,'ask_more','Synthetic routed queue review','seed',%s,%s,true)""",
                (aid, b_id, Jsonb(features), created),
            )
            conn.execute(
                """insert into notifications(community_id,applicant_id,kind,message,is_seed)
                values (%s,%s,'needs_review',%s,true)""",
                (b_id, aid, f"{applicant['name']} needs a lead review."),
            )
            queue_count += 1

        old_declines = [
            (
                "Maya Learns", "maya@example.com", "builder", "skill_gap",
                "demo-maya-learns", 75,
                "I started an accessibility tool for neighborhood events. The first repo has a small working prototype, and I would like practical feedback from London builders.",
            ),
            (
                "Ravi Prototype", "ravi@example.com", "first_timer", "minor_issue",
                "demo-ravi-prototype", 88,
                "I made an early prototype for finding quiet study spaces near local libraries. I am still learning, but I can show the first screen and ask users what is missing.",
            ),
            (
                "Jo Community", "jo@example.com", "builder", "skill_gap",
                "demo-jo-community", 88,
                "I built a small community notice board for nearby residents. The first version is basic, and I hope to improve it after feedback from people who use it.",
            ),
            (
                "Old Scam Example", "old-scam@example.com", "builder", "scam_abuse",
                "demo-old-scam-example", 88,
                "URGENT! You have won a guaranteed prize. Contact me now to claim your bonus reward.",
            ),
        ]
        for name, email, category, reason, handle, age_days, what_build in old_declines:
            reason_time = now - timedelta(days=age_days)
            fixture = DEMO_FIXTURES[handle]
            evidence = {
                key: fixture[key]
                for key in ("github", "devpost", "stopforumspam")
            }
            applicant = {
                "name": name,
                "email": email,
                "phone": f"+44 7700 900{400 + len(name):03d}",
                "github": handle,
                "devpost": None,
                "chat_handle": handle,
                "what_build": what_build,
                "category": category,
            }
            result, features = _score_applicant(
                applicant, evidence, categories, _quota(conn, b_id, category), str(b_id)
            )
            aid = _insert_applicant(
                conn, b_id, name=name, email=email, category=category,
                status="declined", what_build=what_build, created_at=reason_time,
                decided_at=reason_time, reconsider_after=None if reason == "scam_abuse"
                else reason_time + timedelta(days=60),
                decline_reason=reason, recommendation=result["recommendation"],
                features=features, github=handle, chat_handle=handle,
                phone=applicant["phone"],
                previous_decline={
                    "declined_at": reason_time.isoformat(),
                    "reason_category": reason,
                },
                decision_source="auto",
            )
            conn.execute(
                """insert into decisions
                (applicant_id,community_id,verdict,reason_category,note,source,features,created_at,is_seed)
                values (%s,%s,'decline',%s,'Synthetic prior decision','auto',%s,%s,true)""",
                (aid, b_id, reason, Jsonb(features), reason_time),
            )

        # Demo applicants are deterministic on apply and remain available as prior examples.
        a_id = community_ids["shoreditch-builders"]
        for identifier_type, value in [
            ("phone", "+44 7700 900123"), ("handle", "demo-crypto-dave"),
            ("email", "dave.profits@example.com"),
        ]:
            conn.execute(
                """insert into blocklist_entries(identifier_hash,identifier_type,evidence,links,
                reporting_community_id,status,is_seed) values (%s,%s,%s,%s,%s,'confirmed',true)""",
                (identifier_hash(identifier_type, value), identifier_type,
                 "SEED DEMO: 'Guaranteed 100x crypto returns — DM me to invest today.'",
                 ["https://example.com/seed-screenshot-placeholder"], a_id),
            )
        for slug, community_id in community_ids.items():
            identifier = "pending-demo-a@example.com" if slug == "shoreditch-builders" else "pending-demo-b@example.com"
            conn.execute(
                """insert into blocklist_entries(identifier_hash,identifier_type,evidence,links,
                reporting_community_id,status,is_seed) values (%s,'email','Seed pending report',%s,%s,'pending',true)""",
                (identifier_hash("email", identifier), ["https://example.com/seed-placeholder"], community_id),
            )
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-empty", action="store_true")
    seed(if_empty=parser.parse_args().if_empty)
