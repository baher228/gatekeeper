import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

import openai
import pytest

from app.services import llm
from app.routes import misc
from app.services.rules import check_rules


RULES = [{"id": "ship", "text": "Ships a useful project"}]
APPLICANT = {"name": "Taylor", "what_build": "I built a library tool for local readers."}
EVIDENCE = {"github": {}, "devpost": {}}


@pytest.fixture(autouse=True)
def reset_llm_state(monkeypatch):
    monkeypatch.setattr(llm, "calls_made", 0)
    monkeypatch.setattr(llm, "last_error", None)
    monkeypatch.setattr(llm, "last_ok", None)
    monkeypatch.setattr(llm, "MAX_CALLS", 40)


def test_config_defaults_to_gemini(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("CURSOR_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    settings = llm.config()

    assert settings == {
        "provider": "gemini",
        "model": "gemini-3.8-flash",
        "configured": False,
    }


def test_config_defaults_to_cursor_when_key_is_set(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("CURSOR_MODEL", raising=False)

    settings = llm.config()

    assert settings == {
        "provider": "cursor",
        "model": "gemini-3.7-flash-high",
        "configured": True,
    }


def test_cursor_model_override_precedes_cursor_model_fallback(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.7-flash-high")
    monkeypatch.setenv("CURSOR_MODEL", "cursor-grok-4.5-high-fast")

    assert llm.config()["model"] == "gemini-3.7-flash-high"
    monkeypatch.delenv("LLM_MODEL")
    assert llm.config()["model"] == "cursor-grok-4.5-high-fast"


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


def test_health_reports_llm_verification_state(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _query):
            return None

    monkeypatch.setattr(misc, "connect", Connection)

    before = misc.health()["llm"]
    assert before["available"] is False
    assert before["verified"] is False
    assert before["error"] == "not yet verified – no LLM call made since startup"
    assert before["label"] == "gemini · gemini-3.8-flash"
    assert before["calls_made"] == 0
    assert before["max_calls"] == 40

    class SuccessfulClient:
        def __init__(self, **_kwargs):
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=self.create,
                )
            )

        async def create(self, **_kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))]
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    monkeypatch.setattr(openai, "AsyncOpenAI", SuccessfulClient)
    asyncio.run(llm.complete_json([]))
    after_success = misc.health()["llm"]
    assert after_success["available"] is True
    assert after_success["verified"] is True
    assert after_success["error"] is None

    class FailedClient(SuccessfulClient):
        async def create(self, **_kwargs):
            raise RuntimeError("simulated provider failure")

    monkeypatch.setattr(openai, "AsyncOpenAI", FailedClient)
    with pytest.raises(RuntimeError, match="simulated provider failure"):
        asyncio.run(llm.complete_json([]))
    after_failure = misc.health()["llm"]
    assert after_failure["available"] is False
    assert after_failure["verified"] is True
    assert after_failure["error"] == "simulated provider failure"


def test_cursor_health_label_uses_friendly_model_name(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gemini-3.7-flash-high")

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _query):
            return None

    monkeypatch.setattr(misc, "connect", Connection)

    assert misc.health()["llm"]["label"] == "Gemini 3.7 Flash via Cursor"
    monkeypatch.setenv("LLM_MODEL", "cursor-grok-4.5-high-fast")
    assert misc.health()["llm"]["label"] == "Grok 4.5 via Cursor"


def _cursor_process(monkeypatch, envelope, calls=None, on_call=None):
    kill_groups = []

    class Process:
        pid = 12345

        def __init__(self):
            self.returncode = None

        async def wait(self):
            self.returncode = 0
            return self.returncode

    async def create_subprocess_exec(*args, **kwargs):
        if calls is not None:
            calls.append((args, kwargs))
        if on_call is not None:
            on_call(args, kwargs)
        kwargs["stdout"].write(json.dumps(envelope).encode())
        return Process()

    monkeypatch.setattr(llm.os, "killpg", lambda pid, sig: kill_groups.append((pid, sig)))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_subprocess_exec)
    return kill_groups


def _configure_cursor(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "cursor")
    monkeypatch.setenv("CURSOR_API_KEY", "test-cursor-key")
    monkeypatch.setenv("LLM_MODEL", "")
    monkeypatch.setenv("CURSOR_MODEL", "cursor-grok-4.5-high-fast")
    monkeypatch.delenv("CURSOR_AGENT_BIN", raising=False)


def test_cursor_extracts_result_json_and_uses_fresh_empty_workdir(monkeypatch):
    _configure_cursor(monkeypatch)
    calls = []
    workdirs = []
    kill_groups = []

    def check_workdir(_args, kwargs):
        cwd = Path(kwargs["cwd"])
        assert cwd.exists()
        assert cwd.resolve() != Path(__file__).resolve().parents[2]
        assert list(cwd.iterdir()) == []
        workdirs.append(cwd)

    kill_groups = _cursor_process(
        monkeypatch,
        {
            "is_error": False,
            "result": 'Here is the result: {"checks":[{"reason":"brace } in a string"}]} done.',
        },
        calls,
        check_workdir,
    )

    result = asyncio.run(llm.complete_json([
        {"role": "system", "content": "System instructions"},
        {"role": "user", "content": "Applicant details"},
    ]))

    parsed = json.loads(result)
    assert parsed["checks"][0]["reason"] == "brace } in a string"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert not workdirs[0].exists()
    assert args[0] == "~/.local/bin/cursor-agent" or args[0].endswith("/.local/bin/cursor-agent")
    assert args[1:7] == ("-p", "--trust", "--model", "cursor-grok-4.5-high-fast", "--output-format", "json")
    assert "--mode" not in args
    assert "System instructions" in args[-1]
    assert "Applicant details" in args[-1]
    assert args[-1].endswith("Respond with a single JSON object only, no prose, no code fences.")
    assert kwargs["env"]["CURSOR_API_KEY"] == "test-cursor-key"
    assert kwargs["start_new_session"] is True
    assert kwargs["stdout"] is not asyncio.subprocess.PIPE
    assert kwargs["stderr"] is not asyncio.subprocess.PIPE
    assert kill_groups == [(12345, llm.signal.SIGKILL)]


def test_cursor_error_falls_back_with_unavailable_status(monkeypatch):
    _configure_cursor(monkeypatch)
    calls = []
    _cursor_process(
        monkeypatch,
        {"is_error": True, "result": "Cursor reported failure"},
        calls,
    )

    checks, status = asyncio.run(check_rules(RULES, APPLICANT, EVIDENCE))

    assert checks and all(check["source"] == "heuristic" for check in checks)
    assert status["status"] == "unavailable"
    assert status["error"] == "Cursor reported failure"
    assert len(calls) == 2


def test_budget_cap_refuses_second_completion(monkeypatch):
    _configure_cursor(monkeypatch)
    monkeypatch.setenv("LLM_MAX_CALLS", "1")
    monkeypatch.setattr(llm, "MAX_CALLS", int(os.getenv("LLM_MAX_CALLS")))
    calls = []
    _cursor_process(monkeypatch, {"is_error": False, "result": '{"checks": []}'}, calls)

    assert asyncio.run(llm.complete_json([])) == '{"checks": []}'
    with pytest.raises(RuntimeError, match="budget cap reached"):
        asyncio.run(llm.complete_json([]))
    assert len(calls) == 1
    assert llm.calls_made == 1


def test_cursor_failure_uses_at_most_two_attempts(monkeypatch):
    _configure_cursor(monkeypatch)
    calls = []
    _cursor_process(monkeypatch, {"is_error": True, "result": "failure"}, calls)

    with pytest.raises(RuntimeError, match="failure"):
        asyncio.run(llm.complete_json([]))

    assert len(calls) == 2
    assert llm.calls_made == 2


def test_cursor_timeout_kills_process_group_without_waiting_for_output_eof(monkeypatch):
    _configure_cursor(monkeypatch)
    calls = []
    kill_groups = _cursor_process(
        monkeypatch,
        {"is_error": False, "result": '{"checks": []}'},
        calls,
    )

    async def timeout(awaitable, timeout):
        awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(llm.asyncio, "wait_for", timeout)

    with pytest.raises(TimeoutError, match="timed out after 25 seconds"):
        asyncio.run(llm.complete_json([]))

    assert len(calls) == 2
    assert len(kill_groups) == 4
    assert all(group == (12345, llm.signal.SIGKILL) for group in kill_groups)


def test_recheck_reuses_live_checks_without_calling_llm(monkeypatch):
    from app.services import actions

    async def forbidden(_messages):
        raise AssertionError("re-check must not invoke the LLM")

    monkeypatch.setattr(llm, "complete_json", forbidden)
    stored_checks = [{
        "rule_id": "ship", "rule": "Ships a useful project", "score": 0.9,
        "verdict": "pass", "reason": "Describes a concrete project",
        "quote": "built a library tool", "source": "llm",
    }]
    checks, status = asyncio.run(actions._recheck_rule_checks(
        RULES,
        APPLICANT,
        EVIDENCE,
        {
            "llm": {"status": "live", "provider": "cursor", "model": "cursor-grok-4.5-high-fast"},
            "rule_checks": stored_checks,
        },
    ))

    assert checks is stored_checks
    assert status == {
        "status": "cached",
        "provider": "cursor",
        "model": "cursor-grok-4.5-high-fast",
        "error": None,
    }


def test_recheck_falls_back_to_heuristics_without_calling_llm(monkeypatch):
    from app.services import actions

    async def forbidden(_messages):
        raise AssertionError("re-check must not invoke the LLM")

    monkeypatch.setattr(llm, "complete_json", forbidden)
    checks, status = asyncio.run(actions._recheck_rule_checks(
        RULES, APPLICANT, EVIDENCE, {"llm": {"status": "unavailable"}}
    ))

    assert checks and all(check["source"] == "heuristic" for check in checks)
    assert status["status"] == "unavailable"
    assert "only run on live submissions" in status["error"]


def test_recheck_applicant_reuses_live_checks_without_calling_llm(monkeypatch):
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4

    from psycopg.types.json import Jsonb

    from app.db import connect
    from app.services import actions

    async def forbidden(_messages):
        raise AssertionError("re-check must not invoke the LLM")

    async def offline_evidence(_applicant, _fixture=None):
        return {
            "github": {"status": "not_provided", "public_repos": 0, "recent_push_days": None},
            "devpost": {"status": "not_provided", "projects": 0, "wins": 0},
            "stopforumspam": {
                "status": "not_provided",
                "email_appears": False,
                "username_appears": False,
                "confidence": 0,
            },
            "blocklist": {"hit": False, "matches": []},
        }

    monkeypatch.setattr(llm, "complete_json", forbidden)
    monkeypatch.setattr(actions, "gather_evidence", offline_evidence)
    applicant_id = str(uuid4())
    now = datetime.now(timezone.utc)
    stored_checks = [{
        "rule_id": "ship",
        "rule": "Ships a useful project",
        "score": 0.9,
        "verdict": "pass",
        "reason": "Describes a concrete project",
        "quote": "built a library tool",
        "source": "llm",
    }]
    recommendation = {
        "llm": {
            "status": "live",
            "provider": "cursor",
            "model": "cursor-grok-4.5-high-fast",
            "error": None,
        },
        "rule_checks": stored_checks,
        "evidence": {"github": {}, "blocklist": {"matches": []}},
    }

    with connect() as conn:
        community_id = conn.execute(
            "select id from communities where slug='grok-night-london'"
        ).fetchone()["id"]
        conn.execute(
            """insert into applicants(
                id,community_id,name,email,what_build,category,status,decision_source,
                final_score,confidence,decline_reason,decided_at,reconsider_after,
                previous_decline,recommendation,created_at
            ) values (%s,%s,'LLM Cache Recheck','llm-cache-recheck@example.com',
                'A concrete project for local readers.','builder','declined','auto',0.2,0.8,
                'skill_gap',%s,%s,%s,%s,%s)""",
            (
                applicant_id,
                community_id,
                now - timedelta(days=30),
                now - timedelta(days=1),
                Jsonb({"declined_at": (now - timedelta(days=30)).date().isoformat(),
                       "reason_category": "skill_gap"}),
                Jsonb(recommendation),
                now - timedelta(days=30),
            ),
        )

    try:
        result = asyncio.run(actions.recheck_applicant(applicant_id))
        assert result["recommendation"]["llm"]["status"] == "cached"
        assert result["recommendation"]["llm"]["provider"] == "cursor"
        assert result["recommendation"]["rule_checks"][0]["source"] == "llm"
    finally:
        with connect() as conn:
            conn.execute("delete from notifications where applicant_id=%s", (applicant_id,))
            conn.execute("delete from decisions where applicant_id=%s", (applicant_id,))
            conn.execute("delete from applicants where id=%s", (applicant_id,))


def test_eval_run_never_calls_llm(monkeypatch, tmp_path):
    from app import eval as evaluation

    def forbidden(_messages):
        raise AssertionError("evaluation must not invoke the LLM")

    monkeypatch.setattr(llm, "complete_json", forbidden)
    monkeypatch.setattr(evaluation, "DATA_DIR", tmp_path)
    monkeypatch.setattr(evaluation, "TESTSET_PATH", tmp_path / "testset.json")
    monkeypatch.setattr(evaluation, "REPORT_PATH", tmp_path / "eval_report.json")

    report = evaluation.run()

    assert report["test_set"]["n"] == 150
    assert (tmp_path / "eval_report.json").exists()
