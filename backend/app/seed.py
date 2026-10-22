from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from app.db import connect, migrate
from app.services.blocklist import identifier_hash
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
}
DEMO_FIXTURES["demo-maya-learns"]["evidence_now"] = {
    "github": {"status": "simulated", "login": "demo-maya-learns", "account_age_days": 320, "public_repos": 14, "followers": 14, "recent_push_days": 2},
    "devpost": {"status": "simulated", "projects": 2, "wins": 1, "sample": [{"name": "Quiet Hours", "url": "https://example.com/quiet-hours"}]},
    "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
}


def _insert_applicant(conn, community_id, *, name, email, category, status, what_build,
                      created_at, recommendation, github=None, devpost=None, phone=None,
                      chat_handle=None, decline_reason=None, decided_at=None,
                      reconsider_after=None, previous_decline=None, is_seed=True):
    row = conn.execute(
        """insert into applicants
        (community_id,name,email,phone,github,devpost,chat_handle,what_build,category,status,
         decision_source,final_score,confidence,recommendation,features,decline_reason,decided_at,
         reconsider_after,previous_decline,created_at,is_seed)
        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'lead',%s,%s,%s,'{}',%s,%s,%s,%s,%s,%s)
        returning id""",
        (community_id, name, email, phone, github, devpost, chat_handle, what_build, category,
         status, recommendation.get("final_score", 0.5), recommendation.get("confidence", 0.5),
         Jsonb(recommendation), decline_reason, decided_at, reconsider_after,
         Jsonb(previous_decline) if previous_decline else None,
         created_at, is_seed),
    ).fetchone()
    return row["id"]


def _simple_recommendation(status="ask", score=0.5, evidence=None):
    verdict = {"accepted": "accept", "declined": "decline", "waitlisted": "accept", "ask": "ask"}[status]
    return {
        "verdict": verdict, "confidence": 0.65, "final_score": score,
        "reasons": ["Synthetic seed application for demo and evaluation"],
        "route_rule": "seed_fixture", "disagreement": False,
        "llm": {"status": "unavailable", "model": None, "error": "synthetic fixture"},
        "rule_score": score, "rule_checks": [], "history": {"available": False, "p_accept": None, "n_training": 0, "top_features": []},
        "evidence": evidence or {
            "github": {"status": "simulated"}, "devpost": {"status": "simulated"},
            "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
            "blocklist": {"hit": False, "matches": []},
        },
        "quota": {"category": "builder", "quota": 35, "used": 0, "remaining": 35, "bypass_quota": False, "outcome": None, "waitlist_rank": None},
    }


def seed(*, if_empty=False) -> None:
    migrate()
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    with connect() as conn:
        found = conn.execute("select count(*) as n from communities").fetchone()["n"]
        if if_empty and found:
            return
        conn.execute("delete from appeals where entry_id in (select id from blocklist_entries where is_seed)")
        conn.execute("delete from blocklist_entries where is_seed")
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
                reconsider_cooldown_days=60, is_seed=true returning id""",
                (slug, name, description, Jsonb(rules)),
            ).fetchone()
            communities[slug] = row["id"]
        community_ids = communities
        for slug, cid in community_ids.items():
            conn.execute("delete from categories where community_id=%s", (cid,))
            for cat_slug, cat_name, quota, bypass in CATEGORIES:
                conn.execute(
                    "insert into categories(community_id,slug,name,quota,bypass_quota) values (%s,%s,%s,%s,%s)",
                    (cid, cat_slug, cat_name, quota, bypass),
                )

        b_id = community_ids["grok-night-london"]
        # Historical labels are deterministic and deliberately encode writing and recency signals.
        accepted_by_cat = {"builder": 33, "researcher": 12, "first_timer": 9, "mentor": 5, "vip": 2}
        accepted_counts = {slug: 0 for slug in accepted_by_cat}
        for i in range(70):
            cat = CATEGORIES[i % len(CATEGORIES)][0]
            gh_repos = rng.randint(0, 22)
            writing = rng.random()
            pushed = rng.randint(0, 360)
            label_accept = accepted_counts[cat] < accepted_by_cat[cat]
            accepted_counts[cat] += int(label_accept)
            # Introduce deterministic label noise without overflowing accepted quota by swapping labels.
            if rng.random() < 0.1 and i > 10:
                label_accept = not label_accept
            status = "accepted" if label_accept else "declined"
            created = now - timedelta(days=rng.randint(1, 119), minutes=rng.randrange(1440))
            age = rng.randint(30, 3000)
            build = (
                f"I built an AI research assistant and wrote a detailed paper on evaluation, "
                f"sharing feedback with London builders. Writing signal {writing:.2f}."
                if cat == "researcher"
                else f"Shipped a practical AI project with a working demo and clear next steps for users. Build cohort {i}."
            )
            features = {
                "rule_score": round(rng.uniform(0.25, 0.95), 3),
                "rule_min": round(rng.uniform(0.1, 0.8), 3),
                "gh_account_age_years": min(10, age / 365.25),
                "gh_repos_log": __import__("math").log1p(gh_repos),
                "gh_followers_log": __import__("math").log1p(rng.randint(0, 400)),
                "gh_recent_push": int(pushed <= 90),
                "devpost_projects": float(rng.randint(0, 3)),
                "devpost_wins": float(rng.randint(0, 1)),
                "sfs_appears": 0, "has_github": 1, "has_devpost": int(rng.random() > 0.7),
                "what_build_len_log": __import__("math").log1p(len(build)),
            }
            features.update({f"category_{c[0]}": int(cat == c[0]) for c in CATEGORIES})
            score = features["rule_score"]
            evidence = {
                "github": {"status": "simulated", "login": f"history-{i}", "account_age_days": age,
                           "public_repos": gh_repos, "followers": int(__import__("math").expm1(features["gh_followers_log"])),
                           "recent_push_days": pushed},
                "devpost": {"status": "simulated", "projects": int(features["devpost_projects"]), "wins": int(features["devpost_wins"]), "sample": []},
                "stopforumspam": {"status": "simulated", "email_appears": False, "username_appears": False, "confidence": 0},
                "blocklist": {"hit": False, "matches": []},
            }
            rec = _simple_recommendation(status, score, evidence)
            rec["rule_score"] = score
            aid = _insert_applicant(
                conn, b_id, name=f"Seed Builder {i+1:02}", email=f"builder{i}@example.com",
                category=cat, status=status, what_build=build, created_at=created,
                recommendation=rec, github=f"builder-{i}", devpost=None,
                phone=f"+44 7700 900{i+200:03d}", decided_at=created, is_seed=True,
            )
            conn.execute(
                "insert into decisions(applicant_id,community_id,verdict,reason_category,note,source,features,created_at,is_seed) "
                "values (%s,%s,%s,%s,%s,'seed',%s,%s,true)",
                (aid, b_id, "accept" if label_accept else "decline", None if label_accept else "skill_gap",
                 "Synthetic lead label", Jsonb(features), created),
            )

        # Current queue cards.
        for i, handle in enumerate(["demo-sam-research", "demo-queue-1", "demo-queue-2", "demo-queue-3", "demo-queue-4", "demo-queue-5"]):
            fixture = DEMO_FIXTURES.get(handle, {})
            evidence = {k: v for k, v in fixture.items() if k in ("github", "devpost", "stopforumspam")}
            rec = _simple_recommendation("ask", 0.48 + i * 0.01, evidence or None)
            rec["route_rule"] = "low_confidence"
            aid = _insert_applicant(
                conn, b_id, name=f"Queue Applicant {i+1}", email=f"queue{i}@example.com",
                category="researcher" if i % 2 == 0 else "builder", status="ask",
                what_build="I am exploring a practical AI research project and would love to share a working demo and get useful feedback from other London builders.",
                created_at=now - timedelta(hours=10 - i), recommendation=rec,
                github=handle, is_seed=True,
                phone=f"+44 7700 900{i+300:03d}",
            )
            conn.execute(
                """insert into decisions(applicant_id,community_id,verdict,note,source,features,is_seed)
                values (%s,%s,'ask_more','Synthetic lead review requested','seed',%s,true)""",
                (aid, b_id, Jsonb({"rule_score": 0.5, f"category_{'researcher' if i % 2 == 0 else 'builder'}": 1})),
            )

        old_time = now - timedelta(days=75)
        maya_fixture = DEMO_FIXTURES["demo-maya-learns"]
        maya_rec = _simple_recommendation("declined", 0.32, {
            k: maya_fixture[k] for k in ("github", "devpost", "stopforumspam")
        })
        maya_id = _insert_applicant(
            conn, b_id, name="Maya Learns", email="maya@example.com", category="builder",
            status="declined", what_build="Learning to build accessible tools for local communities and documenting my progress.",
            created_at=old_time, decided_at=old_time, reconsider_after=old_time + timedelta(days=60),
            decline_reason="skill_gap", recommendation=maya_rec, github="demo-maya-learns",
            previous_decline={"declined_at": old_time.isoformat(), "reason_category": "skill_gap"},
        )
        conn.execute(
            """insert into decisions(applicant_id,community_id,verdict,reason_category,note,source,features,is_seed)
            values (%s,%s,'decline','skill_gap','Seed decision before evidence improved','seed',%s,true)""",
            (maya_id, b_id, Jsonb({"rule_score": 0.32, "rule_min": 0.2, "category_builder": 1})),
        )
        for name, category, reason in [
            ("Ravi Prototype", "first_timer", "minor_issue"),
            ("Jo Community", "builder", "skill_gap"),
            ("Old Scam Example", "builder", "scam_abuse"),
        ]:
            reason_time = now - timedelta(days=88)
            rec = _simple_recommendation("declined", 0.25, None)
            handle = {
                "Ravi Prototype": "demo-ravi-prototype",
                "Jo Community": "demo-jo-community",
                "Old Scam Example": None,
            }[name]
            fixture = DEMO_FIXTURES.get(handle) if handle else None
            if fixture:
                rec["evidence"] = {k: v for k, v in fixture.items() if k in ("github", "devpost", "stopforumspam")}
            old_id = _insert_applicant(
                conn, b_id, name=name, email=f"{name.split()[0].lower()}@example.com",
                category=category, status="declined", what_build="I want to build something useful for people nearby.",
                created_at=reason_time, decided_at=reason_time,
                reconsider_after=None if reason == "scam_abuse" else reason_time + timedelta(days=60),
                decline_reason=reason, recommendation=rec, github=handle,
                phone=f"+44 7700 900{400+len(name):03d}",
                previous_decline={"declined_at": reason_time.isoformat(), "reason_category": reason},
            )
            conn.execute(
                """insert into decisions(applicant_id,community_id,verdict,reason_category,note,source,features,is_seed)
                values (%s,%s,'decline',%s,'Synthetic prior lead decision','seed',%s,true)""",
                (old_id, b_id, reason, Jsonb({"rule_score": 0.25, "rule_min": 0.1, f"category_{category}": 1})),
            )

        # Demo applicants are deterministic on apply and remain available as prior examples.
        a_id = community_ids["shoreditch-builders"]
        for i in range(2):
            conn.execute(
                "insert into notifications(community_id,applicant_id,kind,message,is_seed) "
                "values (%s,null,'needs_review',%s,true)",
                (b_id, f"Seed queue item {i+1} needs a lead review"),
            )
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
        conn.execute(
            "insert into notifications(community_id,kind,message,is_seed) values (%s,'needs_review','6 applicants are waiting for review.',true)",
            (b_id,),
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-empty", action="store_true")
    seed(if_empty=parser.parse_args().if_empty)
