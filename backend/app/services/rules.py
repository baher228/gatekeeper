from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from pydantic import BaseModel, Field
from typing import Literal


class RuleCheck(BaseModel):
    rule_id: str
    score: float = Field(ge=0, le=1)
    verdict: Literal["pass", "unclear", "fail"]
    reason: str = Field(max_length=200)
    quote: str | None = None


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower())) - {
        "the", "and", "or", "with", "will", "has", "for", "from", "this", "that",
        "are", "you", "your", "into", "who", "a", "an", "to", "of", "in",
    }


def heuristic_checks(rules: list[dict], applicant: dict, evidence: dict) -> list[dict]:
    body = applicant.get("what_build", "")
    body_tokens = _tokens(body)
    combined = " ".join(
        str(v) for v in (applicant.get("github"), applicant.get("devpost"), applicant.get("chat_handle")) if v
    ).lower()
    gh = evidence.get("github", {})
    dp = evidence.get("devpost", {})
    results = []
    for rule in rules:
        words = _tokens(rule.get("text", ""))
        overlap = len(words & body_tokens) / max(1, len(words))
        signals = 0.0
        text = rule.get("text", "").lower()
        if any(w in text for w in ("ship", "repo", "build", "project", "demo")):
            signals += min(0.5, 0.15 * (int(gh.get("public_repos") or 0) > 0) + 0.2 * (int(dp.get("projects") or 0) > 0))
        if any(w in text for w in ("contribute", "feedback", "help", "mentor")) and len(body) >= 120:
            signals += 0.15
        if any(w in text for w in ("london", "based", "regularly")) and "london" in body.lower():
            signals += 0.2
        if any(w in text for w in ("spam", "recruit", "selling", "crypto")) and not re.search(
            r"\b(recruit|selling|pump|airdrop|guaranteed profit)\b", body.lower()
        ):
            signals += 0.2
        score = min(1.0, 0.1 + overlap * 0.65 + signals)
        verdict = "pass" if score >= 0.55 else "unclear" if score >= 0.3 else "fail"
        matched = sorted(words & body_tokens)
        reason = f"matched {', '.join(matched[:4])}" if matched else "little direct overlap"
        if signals:
            reason += "; evidence signals support this rule"
        quote = None
        if matched:
            match = re.search(r"\b" + re.escape(matched[0]) + r"\b", body, re.I)
            if match:
                quote = body[max(0, match.start() - 30) : min(len(body), match.end() + 45)].strip()
        results.append(
            {
                "rule_id": rule.get("id", ""),
                "rule": rule.get("text", ""),
                "score": round(score, 3),
                "verdict": verdict,
                "reason": reason[:150],
                "quote": quote,
                "source": "heuristic",
            }
        )
    return results


@lru_cache(maxsize=4)
def _model_id(api_key: str | None, configured: str | None) -> str | None:
    if configured:
        return configured
    if not api_key:
        return None
    try:
        import httpx

        response = httpx.get(
            "https://api.x.ai/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        response.raise_for_status()
        ids = [m.get("id", "") for m in response.json().get("data", [])]
        candidates = [name for name in ids if "grok-4" in name.lower()]
        return next((name for name in candidates if "fast" in name.lower()), candidates[0] if candidates else None)
    except Exception:
        return None


async def check_rules(rules: list[dict], applicant: dict, evidence: dict) -> tuple[list[dict], dict]:
    key = os.getenv("XAI_API_KEY")
    model = _model_id(key, os.getenv("GROK_MODEL"))
    if not key or not model:
        checks = heuristic_checks(rules, applicant, evidence)
        error = "XAI_API_KEY not configured" if not key else "Grok model discovery failed"
        return checks, {"status": "unavailable", "model": None, "error": error}
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=key, base_url="https://api.x.ai/v1", timeout=5)
        response = await client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "Return JSON with a checks array. Each check: rule_id, score 0-1, verdict pass/unclear/fail, reason <=20 words, quote verbatim or null.",
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"rules": rules, "application": applicant, "evidence": evidence},
                        ensure_ascii=False,
                    ),
                },
            ],
        )
    except Exception as error:
        return heuristic_checks(rules, applicant, evidence), {
            "status": "unavailable", "model": model,
            "error": f"Grok request failed: {type(error).__name__}",
        }
    try:
        parsed = json.loads(response.choices[0].message.content or "")
        raw = parsed if isinstance(parsed, list) else parsed["checks"]
        checked = [RuleCheck.model_validate(item).model_dump() for item in raw]
        if any(len(item["reason"].split()) > 20 for item in checked):
            raise ValueError("reason exceeds 20 words")
        application_text = " ".join(str(value) for value in applicant.values() if value)
        if any(item.get("quote") is not None and item["quote"] not in application_text for item in checked):
            raise ValueError("non-verbatim quote")
        by_id = {item["id"]: item["text"] for item in rules}
        for item in checked:
            item.update(rule=by_id.get(item["rule_id"], ""), source="llm")
        return checked, {"status": "live", "model": model, "error": None}
    except Exception:
        checks = heuristic_checks(rules, applicant, evidence)
        return checks, {"status": "unavailable", "model": model, "error": "invalid structured output"}


def calculate_rule_score(checks: list[dict], evidence: dict, category: str) -> float:
    """Blend rule fit (60%) and evidence (40%); first-timers receive less footprint weight."""
    rules_mean = sum(float(item["score"]) for item in checks) / max(1, len(checks))
    gh, dp = evidence.get("github", {}), evidence.get("devpost", {})
    activity = min(1, (int(gh.get("public_repos") or 0) / 10) * 0.45 + (int(dp.get("projects") or 0) / 3) * 0.35 + (int(dp.get("wins") or 0) * 0.2))
    if gh.get("recent_push_days") is not None and gh["recent_push_days"] <= 180:
        activity = min(1, activity + 0.15)
    evidence_weight = 0.15 if category == "first_timer" else 0.4
    rule_weight = 1 - evidence_weight
    evidence_score = activity if category != "first_timer" else 0.5 + 0.5 * activity
    return round(rule_weight * rules_mean + evidence_weight * evidence_score, 4)
