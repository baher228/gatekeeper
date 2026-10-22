import asyncio
import json
import os
import shutil
import tempfile
from functools import lru_cache

import httpx
import openai


PROVIDERS = {
    "gemini": {
        "key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.8-flash",
    },
    "grok": {
        "key_env": "XAI_API_KEY",
        "base_url": "https://api.x.ai/v1",
        "model_env": "GROK_MODEL",
        "default_model": None,
    },
    "cursor": {
        "key_env": "CURSOR_API_KEY",
        "model_env": "LLM_MODEL",
        "fallback_model_env": "CURSOR_MODEL",
        "default_model": "gemini-3.7-flash-high",
        "binary_env": "CURSOR_AGENT_BIN",
        "default_binary": "~/.local/bin/cursor-agent",
    },
}

last_error: str | None = None
last_ok: bool | None = None
calls_made = 0
MAX_CALLS = int(os.getenv("LLM_MAX_CALLS", "40"))


@lru_cache(maxsize=1)
def _model_id(api_key: str) -> str | None:
    try:
        response = httpx.get(
            f"{PROVIDERS['grok']['base_url']}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=5,
        )
        response.raise_for_status()
        models = response.json().get("data", [])
        return next((model["id"] for model in models if model.get("id")), None)
    except Exception:
        return None


def config() -> dict:
    provider_setting = os.getenv("LLM_PROVIDER")
    if provider_setting and provider_setting.strip():
        provider = provider_setting.strip().lower()
    else:
        provider = "cursor" if os.getenv("CURSOR_API_KEY") else "gemini"
    settings = PROVIDERS.get(provider)
    if not settings:
        return {"provider": provider, "model": None, "configured": False}

    model = os.getenv(settings["model_env"])
    fallback_model_env = settings.get("fallback_model_env")
    if not model and fallback_model_env:
        model = os.getenv(fallback_model_env)
    model = model or settings["default_model"]
    if provider == "grok" and not model:
        api_key = os.getenv(settings["key_env"])
        model = _model_id(api_key) if api_key else None
    return {
        "provider": provider,
        "model": model,
        "configured": bool(os.getenv(settings["key_env"]) and model),
    }


def configuration_error(settings: dict) -> str | None:
    provider_settings = PROVIDERS.get(settings["provider"])
    if not provider_settings:
        return f"Unsupported LLM_PROVIDER: {settings['provider']}"
    if not os.getenv(provider_settings["key_env"]):
        return f"{provider_settings['key_env']} not configured"
    if not settings["model"]:
        return f"{provider_settings['model_env']} not configured"
    return None


def _redact_secrets(message: str) -> str:
    for key_name in ("CURSOR_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"):
        secret = os.getenv(key_name)
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def _short_error(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    body = getattr(error, "body", None)
    if isinstance(body, list) and body:
        body = body[0]
    if isinstance(body, dict):
        nested = body.get("error")
        if isinstance(nested, dict) and nested.get("message"):
            message = str(nested["message"])
        elif body.get("message"):
            message = str(body["message"])
        else:
            message = str(error)
    else:
        message = str(error)
    if status_code and not message.startswith(str(status_code)):
        message = f"{status_code} {message}"
    message = _redact_secrets(message)
    return message[:160]


def _first_json_object(text: str) -> str:
    start = text.find("{")
    if start < 0:
        raise ValueError("Cursor result did not contain a JSON object")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start:index + 1]
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError("Cursor result was not a JSON object")
                return candidate
    raise ValueError("Cursor result contained an incomplete JSON object")


def _cursor_prompt(messages: list[dict]) -> str:
    parts = [
        str(message.get("content", ""))
        for message in messages
        if message.get("content") is not None
    ]
    parts.append("Respond with a single JSON object only, no prose, no code fences.")
    return "\n\n".join(parts)


async def _complete_with_cursor(messages: list[dict], settings: dict) -> str:
    provider_settings = PROVIDERS["cursor"]
    binary = os.path.expanduser(
        os.getenv(provider_settings["binary_env"]) or provider_settings["default_binary"]
    )
    workdir = tempfile.mkdtemp(prefix="gatekeeper-llm-")
    process = None
    try:
        env = os.environ.copy()
        api_key = os.getenv(provider_settings["key_env"])
        if api_key:
            env[provider_settings["key_env"]] = api_key
        process = await asyncio.create_subprocess_exec(
            binary,
            "-p",
            "--trust",
            "--model",
            settings["model"],
            "--output-format",
            "json",
            _cursor_prompt(messages),
            cwd=workdir,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=60)
        except asyncio.TimeoutError as error:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
            raise TimeoutError("Cursor agent timed out after 60 seconds") from error

        if process.returncode != 0:
            raise RuntimeError(f"Cursor agent exited with status {process.returncode}")
        try:
            response = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Cursor agent returned invalid JSON") from error
        if not isinstance(response, dict):
            raise RuntimeError("Cursor agent returned an invalid response")
        if response.get("is_error"):
            raise RuntimeError(
                _redact_secrets(str(response.get("result") or "Cursor agent reported an error"))
            )
        if "result" not in response or response["result"] is None:
            raise RuntimeError("Cursor agent response is missing result")
        if not isinstance(response["result"], str):
            raise RuntimeError("Cursor agent result was not text")
        return _first_json_object(response["result"])
    finally:
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
        shutil.rmtree(workdir, ignore_errors=True)


async def _complete_once(messages: list[dict], settings: dict) -> str:
    provider = settings["provider"]
    if provider == "cursor":
        return await _complete_with_cursor(messages, settings)
    provider_settings = PROVIDERS[provider]
    async with openai.AsyncOpenAI(
        api_key=os.getenv(provider_settings["key_env"]),
        base_url=provider_settings["base_url"],
        timeout=10,
        max_retries=0,
    ) as client:
        response = await client.chat.completions.create(
            model=settings["model"],
            messages=messages,
            response_format={"type": "json_object"},
        )
    content = response.choices[0].message.content
    if content is None:
        raise ValueError("Provider returned empty structured output")
    return content


async def complete_json(messages: list[dict]) -> str:
    global calls_made, last_error, last_ok
    last_error = None
    if calls_made >= MAX_CALLS:
        last_error = f"LLM budget cap reached ({MAX_CALLS} calls)"
        last_ok = False
        raise RuntimeError(last_error)
    settings = config()
    error = configuration_error(settings)
    if error:
        last_error = error
        last_ok = False
        raise RuntimeError(error)

    for attempt in range(2):
        if calls_made >= MAX_CALLS:
            last_error = f"LLM budget cap reached ({MAX_CALLS} calls)"
            last_ok = False
            raise RuntimeError(last_error)
        calls_made += 1
        try:
            result = await _complete_once(messages, settings)
        except Exception as error:
            last_error = _short_error(error)
            last_ok = False
            if attempt == 0:
                continue
            raise
        last_error = None
        last_ok = True
        return result

    raise RuntimeError(last_error or "LLM completion failed")
