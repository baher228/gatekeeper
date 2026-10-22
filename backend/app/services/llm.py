from __future__ import annotations

import os
from functools import lru_cache


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
}

last_error: str | None = None


@lru_cache(maxsize=8)
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
        ids = [model.get("id", "") for model in response.json().get("data", [])]
        candidates = [name for name in ids if "grok-4" in name.lower()]
        return next(
            (name for name in candidates if "fast" in name.lower()),
            candidates[0] if candidates else None,
        )
    except Exception:
        return None


def config() -> dict[str, str | bool | None]:
    provider = os.getenv("LLM_PROVIDER", "gemini").strip().lower()
    settings = PROVIDERS.get(provider)
    if settings is None:
        return {"provider": provider, "model": None, "configured": False}

    api_key = os.getenv(settings["key_env"])
    if provider == "grok":
        model = _model_id(api_key, os.getenv(settings["model_env"]))
    else:
        model = os.getenv(settings["model_env"]) or settings["default_model"]
    return {"provider": provider, "model": model, "configured": bool(api_key and model)}


def configuration_error(settings: dict[str, str | bool | None]) -> str:
    provider = str(settings["provider"])
    provider_settings = PROVIDERS.get(provider)
    if provider_settings is None:
        return f"Unsupported LLM_PROVIDER: {provider}"
    if not os.getenv(provider_settings["key_env"]):
        return f"{provider_settings['key_env']} not configured"
    if provider == "grok":
        return "Grok model discovery failed"
    return f"{provider} model not configured"


def _short_error(error: Exception) -> str:
    status_code = getattr(error, "status_code", None)
    body = getattr(error, "body", None)
    message = None
    detail = body[0] if isinstance(body, list) and body else body
    if isinstance(detail, dict):
        nested = detail.get("error", detail)
        if isinstance(nested, dict):
            message = nested.get("message")
    if not message:
        message = getattr(error, "message", None)
    if isinstance(message, dict):
        message = message.get("message") or str(message)
    if not message:
        message = str(error)
    message = " ".join(str(message).split())
    text = f"{status_code} {message}" if status_code is not None else message
    return text[:160]


async def complete_json(messages: list[dict]) -> str:
    global last_error

    last_error = None
    settings = config()
    if not settings["configured"]:
        last_error = configuration_error(settings)
        raise RuntimeError(last_error)

    provider = str(settings["provider"])
    provider_settings = PROVIDERS[provider]
    try:
        from openai import AsyncOpenAI

        async with AsyncOpenAI(
            api_key=os.getenv(provider_settings["key_env"]),
            base_url=provider_settings["base_url"],
            timeout=10,
        ) as client:
            response = await client.chat.completions.create(
                model=settings["model"],
                response_format={"type": "json_object"},
                messages=messages,
            )
        return response.choices[0].message.content or ""
    except Exception as error:
        last_error = _short_error(error)
        raise
