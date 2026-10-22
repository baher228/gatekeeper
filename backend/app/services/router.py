from __future__ import annotations


def route(
    applicant: dict,
    checks: list[dict],
    rule_score: float,
    evidence: dict,
    history: dict,
    quota: dict,
    blocklist_matches: list[dict] | None = None,
    cooldown_days: int = 60,
) -> dict:
    """Apply ordered safety, completeness, score, and category-capacity decisions."""
    matches = blocklist_matches or []
    reasons: list[str] = []
    stopforum = evidence.get("stopforumspam", {})
    gh, dp = evidence.get("github", {}), evidence.get("devpost", {})
    p_accept = history.get("p_accept")
    model_available = bool(history.get("available") and p_accept is not None)
    final_score = float(rule_score) if not model_available else 0.5 * float(rule_score) + 0.5 * float(p_accept)
    route_rule = "low_confidence"
    verdict = "ask"
    reason_category = None
    confidence = 0.2
    disagreement = model_available and ((rule_score >= 0.5) != (p_accept >= 0.5)) and abs(rule_score - p_accept) > 0.25

    confirmed = [m for m in matches if m.get("status") == "confirmed"]
    unconfirmed = [m for m in matches if m.get("status") in ("pending", "appealed")]
    if confirmed:
        hit = confirmed[0]
        reporter = hit.get("reporting_community") or "another community"
        kind = hit.get("identifier_type", "identifier")
        reasons.append(f"Matched confirmed blocklist report from {reporter} ({kind})")
        verdict, route_rule, reason_category, confidence = "decline", "blocklist_confirmed", "scam_abuse", 0.95
    elif unconfirmed:
        reasons.append("Matched an unconfirmed blocklist report; lead review required")
        verdict, route_rule, confidence = "ask", "blocklist_unconfirmed", 0.75
    elif (stopforum.get("email_appears") or stopforum.get("username_appears")) and float(stopforum.get("confidence", 0) or 0) >= 50:
        reasons.append(f"StopForumSpam signal ({float(stopforum.get('confidence', 0)):.0f}% confidence); requires review")
        verdict, route_rule, confidence = "ask", "spam_signal", 0.7
    elif len(applicant.get("what_build", "")) < 30 and not applicant.get("github") and not applicant.get("devpost"):
        reasons.append("Application is too brief and has no GitHub or Devpost profile")
        verdict, route_rule, reason_category, confidence = "decline", "incomplete", "minor_issue", 0.8
    elif disagreement:
        reasons.append(
            f"Scored at submission by model trained on {history.get('n_training', 0)} decisions; it disagrees with application evidence"
        )
        verdict, route_rule, confidence = "ask", "disagreement", 0.65
    else:
        if gh.get("status") in ("live", "simulated") and gh.get("account_age_days") is not None:
            reasons.append(
                f"GitHub: {round(gh['account_age_days']/365.25, 1)}y old, {gh.get('public_repos', 0)} repos"
                + (f", pushed {gh['recent_push_days']}d ago" if gh.get("recent_push_days") is not None else "")
            )
        if int(dp.get("projects") or 0):
            reasons.append(f"Devpost: {dp.get('projects')} projects, {dp.get('wins', 0)} wins")
        for check in checks:
            reasons.append(f"Rule '{check.get('rule', check.get('rule_id', ''))}' {check.get('verdict')}: {check.get('reason', '')}")
        if model_available:
            reasons.append(
                f"Scored at submission by model trained on {history.get('n_training', 0)} decisions; P(accept)={p_accept:.2f}"
            )
        if final_score >= 0.62:
            verdict, route_rule = "accept", "score_accept"
        elif final_score <= 0.38:
            verdict, route_rule = "decline", "score_decline"
            weak_evidence = not (
                int(gh.get("public_repos") or 0) > 0
                or int(dp.get("projects") or 0) > 0
                or int(dp.get("wins") or 0) > 0
            )
            reason_category = "skill_gap" if weak_evidence else "rules_mismatch"
        confidence = min(
            1.0,
            abs(final_score - 0.5) * 2
            + 0.2 * int(model_available and ((rule_score >= 0.5) == (p_accept >= 0.5))),
        )

    quota_outcome = None
    waitlist_rank = None
    status = {"accept": "accepted", "decline": "declined", "ask": "ask"}[verdict]
    if verdict == "accept":
        if quota.get("bypass_quota") or int(quota.get("remaining", 0)) > 0:
            quota_outcome = "seat"
        else:
            status = "waitlisted"
            quota_outcome = "waitlisted"
            waitlist_rank = int(quota.get("waitlisted", 0)) + 1
            reason_category = "capacity"
            reasons.insert(0, "Category is full; added to the waitlist")

    recommendation = {
        "verdict": verdict,
        "confidence": round(float(confidence), 4),
        "final_score": round(float(final_score), 4),
        "reasons": reasons[:12],
        "route_rule": route_rule,
        "disagreement": bool(disagreement),
        "llm": {"status": "unavailable", "provider": None, "model": None, "error": None},
        "rule_score": round(float(rule_score), 4),
        "rule_checks": checks,
        "history": {
            "available": model_available,
            "p_accept": None if p_accept is None else round(float(p_accept), 4),
            "n_training": history.get("n_training", 0),
            "top_features": history.get("top_features", []),
        },
        "evidence": {**evidence, "blocklist": {"hit": bool(matches), "matches": matches}},
        "quota": {
            "category": quota.get("slug", applicant.get("category")),
            "quota": quota.get("quota", 0),
            "used": quota.get("used", 0),
            "remaining": quota.get("remaining", 0),
            "bypass_quota": quota.get("bypass_quota", False),
            "outcome": quota_outcome,
            "waitlist_rank": waitlist_rank,
        },
        "decline_reason": reason_category,
        "reconsider_after_days": cooldown_days
        if verdict == "decline" and reason_category in ("skill_gap", "minor_issue", "capacity")
        else None,
    }
    return {"status": status, "recommendation": recommendation, "decline_reason": reason_category}
