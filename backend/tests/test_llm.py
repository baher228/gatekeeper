import asyncio
import json

from app.services import llm
from app.services.rules import check_rules


RULES = [{"id": "ship", "text": "Ships a useful project"}]
APPLICANT = {"name": "Taylor", "what_build": "I built a library tool for local readers."}
EVIDENCE = {"github": {}, "devpost": {}}


def test_config_defaults_to_gemini(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    settings = llm.config()

    assert settings == {
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "configured": False,
    }


def test_config_uses_configured_grok_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "grok")
    monkeypatch.setenv("XAI_API_KEY", "test-key")
    monkeypatch.setenv("GROK_MODEL", "grok-4-fast-test")

    settings = llm.config()

    assert settings == {
        "provider": "grok",
        "model": "grok-4-fast-test",
        "configured": True,
    }


def test_api_error_formats_nested_provider_message():
    class ProviderError(Exception):
        status_code = 402
        body = [{"error": {"message": "Your prepayment credits are depleted"}}]
        message = "Error code: 402 - provider response"

    assert llm._short_error(ProviderError()) == "402 Your prepayment credits are depleted"


def test_check_rules_falls_back_with_provider_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "last_error", None)

    async def fail(_messages):
        llm.last_error = "402 Your prepayment credits are depleted"
        raise RuntimeError("provider error")

    monkeypatch.setattr(llm, "complete_json", fail)
    checks, status = asyncio.run(check_rules(RULES, APPLICANT, EVIDENCE))

    assert checks and all(check["source"] == "heuristic" for check in checks)
    assert status == {
        "status": "unavailable",
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "error": "402 Your prepayment credits are depleted",
    }


def test_check_rules_falls_back_on_invalid_json(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    async def invalid(_messages):
        return "not JSON"

    monkeypatch.setattr(llm, "complete_json", invalid)
    checks, status = asyncio.run(check_rules(RULES, APPLICANT, EVIDENCE))

    assert checks and all(check["source"] == "heuristic" for check in checks)
    assert status == {
        "status": "unavailable",
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "error": "invalid structured output",
    }


def test_check_rules_accepts_valid_json_with_verbatim_quote(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    response = json.dumps({
        "checks": [{
            "rule_id": "ship",
            "score": 0.9,
            "verdict": "pass",
            "reason": "Describes a concrete project",
            "quote": "built a library tool",
        }]
    })

    async def complete(_messages):
        return response

    monkeypatch.setattr(llm, "complete_json", complete)
    checks, status = asyncio.run(check_rules(RULES, APPLICANT, EVIDENCE))

    assert status == {
        "status": "live",
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "error": None,
    }
    assert checks[0]["source"] == "llm"
    assert checks[0]["quote"] == "built a library tool"
