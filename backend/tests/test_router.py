from app.services.router import route


def make_route(*, score=0.5, evidence=None, history=None, quota=None, matches=None, applicant=None):
    return route(
        applicant or {"what_build": "A sufficiently detailed application that describes a real project."},
        [{"rule_id": "ship", "rule": "Ships things", "score": score, "verdict": "pass", "reason": "matched project"}],
        score,
        evidence or {"github": {"status": "simulated", "public_repos": 1}},
        history or {"available": False, "p_accept": None, "n_training": 0, "top_features": []},
        quota or {"slug": "builder", "quota": 10, "used": 0, "remaining": 10, "waitlisted": 0, "bypass_quota": False},
        matches,
    )


def test_confirmed_blocklist_declines_and_records_priority_reason():
    result = make_route(matches=[{"status": "confirmed", "identifier_type": "phone", "reporting_community": "Shoreditch Builders Club"}])
    assert result["status"] == "declined"
    assert result["recommendation"]["route_rule"] == "blocklist_confirmed"
    assert result["decline_reason"] == "scam_abuse"
    assert result["recommendation"]["confidence"] == 0.95


def test_pending_and_appealed_blocklist_require_review():
    for status in ("pending", "appealed"):
        result = make_route(matches=[{"status": status}])
        assert result["status"] == "ask"
        assert result["recommendation"]["route_rule"] == "blocklist_unconfirmed"


def test_stopforumspam_signal_asks_never_declines():
    result = make_route(evidence={"stopforumspam": {"email_appears": True, "confidence": 65}})
    assert result["status"] == "ask"
    assert result["recommendation"]["route_rule"] == "spam_signal"


def test_incomplete_application_declines_minor_issue():
    result = make_route(applicant={"what_build": "tiny", "github": None, "devpost": None})
    assert result["status"] == "declined"
    assert result["decline_reason"] == "minor_issue"
    assert result["recommendation"]["route_rule"] == "incomplete"


def test_model_disagreement_routes_to_ask():
    result = make_route(
        score=0.85,
        history={"available": True, "p_accept": 0.4, "n_training": 30, "top_features": []},
    )
    assert result["status"] == "ask"
    assert result["recommendation"]["route_rule"] == "disagreement"


def test_score_thresholds_decline_and_accept():
    decline = make_route(score=0.2, evidence={"github": {"public_repos": 0}, "devpost": {"projects": 0}})
    accept = make_route(score=0.8)
    assert decline["status"] == "declined"
    assert decline["decline_reason"] == "skill_gap"
    assert accept["status"] == "accepted"
    assert accept["recommendation"]["quota"]["outcome"] == "seat"


def test_quota_waitlists_accepts_and_vip_bypasses():
    full = make_route(
        score=0.9,
        quota={"slug": "builder", "quota": 1, "used": 1, "remaining": 0, "waitlisted": 2, "bypass_quota": False},
    )
    vip = make_route(
        score=0.9,
        quota={"slug": "vip", "quota": 1, "used": 1, "remaining": 0, "waitlisted": 0, "bypass_quota": True},
    )
    assert full["status"] == "waitlisted"
    assert full["decline_reason"] == "capacity"
    assert full["recommendation"]["quota"]["waitlist_rank"] == 3
    assert vip["status"] == "accepted"
    assert vip["recommendation"]["quota"]["outcome"] == "seat"
