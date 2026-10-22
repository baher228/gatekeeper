from datetime import datetime, timedelta, timezone

import pytest

from app.db import connect
from app.services.applications import applicant_detail


def test_demo_applications_are_deterministic(client):
    dave = client.post(
        "/api/communities/grok-night-london/apply",
        json={
            "name": "Demo Dave", "email": "dave.profits@example.com", "phone": "+44 7700 900123",
            "chat_handle": "demo-crypto-dave", "what_build": "A token with guaranteed 100x profits, DM me today.",
            "category": "builder",
        },
    )
    assert dave.status_code == 200, dave.text
    assert dave.json()["status"] == "declined"
    assert dave.json()["recommendation"]["route_rule"] == "blocklist_confirmed"

    ada = client.post(
        "/api/communities/grok-night-london/apply",
        json={
            "name": "Ada Ships", "email": "ada@example.com", "github": "demo-ada-ships",
            "devpost": "ada-ships", "chat_handle": "demo-ada-ships",
            "what_build": "I shipped a practical AI demo for London users. The repo includes a working product, tests, and a clear roadmap. I will share the demo and help other builders with feedback.",
            "category": "builder",
        },
    )
    assert ada.status_code == 200, ada.text
    assert ada.json()["status"] in ("accepted", "waitlisted")


def test_reconsideration_requires_due_date_and_never_allows_scams(client):
    with connect() as conn:
        community = conn.execute("select id from communities where slug='grok-night-london'").fetchone()["id"]
        now = datetime.now(timezone.utc)
        rows = []
        for name, reason, due in [
            ("Cooldown Test", "skill_gap", now + timedelta(days=1)),
            ("Scam Cooldown Test", "scam_abuse", now - timedelta(days=1)),
        ]:
            rows.append(conn.execute(
                """insert into applicants(community_id,name,email,what_build,category,status,decision_source,
                final_score,confidence,decline_reason,decided_at,reconsider_after,created_at)
                values (%s,%s,%s,'A detailed application that explains the project.', 'builder','declined',
                'auto',0.2,0.8,%s,%s,%s,%s) returning id""",
                (community, name, f"{name.lower().replace(' ', '')}@example.com", reason, now, due, now),
            ).fetchone()["id"])
    before = client.post(f"/api/applicants/{rows[0]}/recheck")
    scam = client.post(f"/api/applicants/{rows[1]}/recheck")
    assert before.status_code == 400
    assert "available after" in before.json()["detail"]
    assert scam.status_code == 400
    assert "not eligible" in scam.json()["detail"]


def test_eligible_seed_reconsideration_updates_evidence_and_notifies(client):
    with connect() as conn:
        row = conn.execute(
            "select id from applicants where github='demo-maya-learns' and is_seed=true limit 1"
        ).fetchone()
    response = client.post(f"/api/applicants/{row['id']}/recheck")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["reconsidered"] is True
    assert detail["status"] in ("accepted", "waitlisted", "ask")
    assert "14 repos" in detail["reconsideration"]["note"]
    notifications = client.get("/api/communities/grok-night-london/notifications").json()
    assert any(item["kind"] == "reconsidered" and item["applicant_id"] == str(row["id"]) for item in notifications)


def test_applicant_routes_and_decline_validation(client):
    response = client.get("/api/communities/grok-night-london/queue")
    assert response.status_code == 200
    assert response.json()
    missing = client.get("/api/applicants/00000000-0000-0000-0000-000000000000")
    assert missing.status_code == 404


def test_seeded_queue_cards_have_real_recommendations(client):
    response = client.get("/api/communities/grok-night-london/queue")

    assert response.status_code == 200, response.text
    applicants = response.json()
    assert len(applicants) == 6
    for applicant in applicants:
        recommendation = applicant["recommendation"]
        assert recommendation["history"]["available"] is True
        assert recommendation["rule_checks"]


def test_seed_history_model_has_positive_build_signal(client):
    from app.services.history import train_model

    with connect() as conn:
        community_id = conn.execute(
            "select id from communities where slug='grok-night-london'"
        ).fetchone()["id"]
    model = train_model(str(community_id))
    weights = {item["feature"]: item["weight"] for item in model["coefficients"]}

    assert model["available"] is True
    assert model["n_decisions"] == 120
    assert weights["rule_score"] > 0 or weights["gh_repos_log"] > 0


def test_message_check_uses_cached_sms_model(client, monkeypatch):
    from app.services import message_classifier

    rows = [
        {"text": "claim your free prize now", "label": "spam"},
        {"text": "urgent winner call now", "label": "spam"},
        {"text": "free cash reward guaranteed", "label": "spam"},
        {"text": "limited offer claim today", "label": "spam"},
        {"text": "win a bonus prize", "label": "spam"},
        {"text": "are we still meeting for lunch", "label": "ham"},
        {"text": "please call me when you arrive", "label": "ham"},
        {"text": "thanks for your help yesterday", "label": "ham"},
        {"text": "the project meeting starts at noon", "label": "ham"},
        {"text": "see you at the station later", "label": "ham"},
    ]

    async def load_rows():
        return rows

    monkeypatch.setattr(message_classifier, "_MODEL", None)
    monkeypatch.setattr(message_classifier, "_load_training_rows", load_rows)
    response = client.post(
        "/api/messages/check",
        json={"text": "urgent, claim your free cash prize"},
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["label"] == "spam"
    assert result["scam_probability"] > 0.5
    assert result["top_terms"]
    assert "review it" in result["draft_removal"]
