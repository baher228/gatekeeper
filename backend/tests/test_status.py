from urllib.parse import urlencode
from uuid import uuid4

from app.db import connect


ALLOWED_KEYS = {
    "name",
    "community_name",
    "community_slug",
    "category",
    "decision",
    "waitlist_position",
    "lead_question",
    "applicant_reply",
    "applicant_reply_at",
    "message",
    "invite_url",
    "appeal_url",
}


def _seed_applicant(status: str):
    with connect() as conn:
        return conn.execute(
            """select a.id,a.status_token,a.lead_question,a.applicant_reply,a.applicant_reply_at
            from applicants a join communities c on c.id=a.community_id
            where c.slug='grok-night-london' and a.is_seed and a.status=%s
            order by a.created_at limit 1""",
            (status,),
        ).fetchone()


def test_status_token_returns_only_public_fields(client):
    applicant = _seed_applicant("ask")
    assert applicant and applicant["status_token"]
    response = client.get(f"/api/status/{applicant['status_token']}")
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == ALLOWED_KEYS
    assert not {"final_score", "recommendation", "email", "notes", "flags"} & result.keys()
    assert result["decision"] == "ask"

    missing = client.get(f"/api/status/{uuid4().hex}")
    assert missing.status_code == 404


def test_status_reply_round_trip_and_validation(client):
    applicant = _seed_applicant("ask")
    assert applicant and applicant["status_token"]
    token = applicant["status_token"]
    try:
        response = client.post(
            f"/api/status/{token}/reply",
            json={"text": "  Could I bring a project demo?  "},
        )
        assert response.status_code == 200, response.text
        assert response.json()["applicant_reply"] == "Could I bring a project demo?"
        assert response.json()["applicant_reply_at"]

        fetched = client.get(f"/api/status/{token}")
        assert fetched.json()["applicant_reply"] == "Could I bring a project demo?"
        assert fetched.json()["applicant_reply_at"]
        assert client.post(f"/api/status/{token}/reply", json={"text": "   "}).status_code == 422
        assert client.post(
            f"/api/status/{token}/reply", json={"text": "x" * 1001}
        ).status_code == 422
    finally:
        with connect() as conn:
            conn.execute(
                """update applicants set applicant_reply=%s,applicant_reply_at=%s
                where id=%s""",
                (
                    applicant["applicant_reply"],
                    applicant["applicant_reply_at"],
                    applicant["id"],
                ),
            )


def test_invite_url_is_accepted_only_and_encodes_name(client, monkeypatch):
    monkeypatch.delenv("MEMBER_NETWORK_URL", raising=False)
    ask = _seed_applicant("ask")
    accepted = _seed_applicant("accepted")
    assert ask and accepted

    ask_status = client.get(f"/api/status/{ask['status_token']}").json()
    accepted_status = client.get(f"/api/status/{accepted['status_token']}").json()
    assert ask_status["invite_url"] is None
    assert accepted_status["invite_url"].startswith("http://localhost:5174/join?")
    assert "from=gatekeeper" in accepted_status["invite_url"]
    assert urlencode({"name": accepted_status["name"]}) in accepted_status["invite_url"]


def test_lead_question_is_available_in_status_and_applicant_detail(client):
    applicant = _seed_applicant("ask")
    assert applicant
    missing = client.post(
        f"/api/applicants/{uuid4()}/question",
        json={"question": "A question for nobody"},
    )
    assert missing.status_code == 404
    invalid_id = client.post(
        "/api/applicants/not-a-uuid/question",
        json={"question": "A question for nobody"},
    )
    assert invalid_id.status_code == 404
    try:
        response = client.post(
            f"/api/applicants/{applicant['id']}/question",
            json={"question": "  Can you share a demo link?  "},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True, "lead_question": "Can you share a demo link?"}

        public = client.get(f"/api/status/{applicant['status_token']}").json()
        detail = client.get(f"/api/applicants/{applicant['id']}").json()
        assert public["lead_question"] == "Can you share a demo link?"
        assert detail["lead_question"] == "Can you share a demo link?"
        assert detail["status_token"] == applicant["status_token"]
    finally:
        with connect() as conn:
            conn.execute(
                "update applicants set lead_question=%s where id=%s",
                (applicant["lead_question"], applicant["id"]),
            )


def test_application_response_includes_status_token(client, monkeypatch):
    from app.services import applications

    async def fake_evidence(_applicant, _fixture):
        return {
            "github": {"status": "not_provided"},
            "devpost": {"status": "not_provided"},
            "stopforumspam": {"status": "not_provided"},
        }

    async def fake_rules(_rules, _applicant, _evidence):
        return [], {"status": "unavailable", "provider": None, "model": None, "error": None}

    monkeypatch.setattr(applications, "gather_evidence", fake_evidence)
    monkeypatch.setattr(applications, "check_rules", fake_rules)
    response = client.post(
        "/api/communities/grok-night-london/apply",
        json={
            "name": "Status Token Test",
            "email": "status-token-test@example.test",
            "what_build": "A project with a detailed and useful description for reviewers.",
            "category": "builder",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status_token"]
    assert result["lead_question"] is None
    assert result["applicant_reply"] is None

    with connect() as conn:
        conn.execute("delete from applicants where id=%s", (result["id"],))
