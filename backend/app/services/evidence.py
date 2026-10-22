from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx


def _parse_date(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - dt).days)
    except ValueError:
        return None


async def github_evidence(login: str | None) -> dict:
    if not login:
        return {"status": "not_provided"}
    headers = {"Accept": "application/vnd.github+json"}
    if os.getenv("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"https://api.github.com/users/{quote(login)}", headers=headers
            )
            if response.status_code == 404:
                return {"status": "not_found", "login": login}
            response.raise_for_status()
            data = response.json()
            events_response = await client.get(
                f"https://api.github.com/users/{quote(login)}/events/public?per_page=100",
                headers=headers,
            )
            recent = None
            if events_response.is_success:
                ages = [
                    age
                    for event in events_response.json()
                    if event.get("type") == "PushEvent"
                    if (age := _parse_date(event.get("created_at"))) is not None
                ]
                recent = min(ages) if ages else None
            return {
                "status": "live",
                "login": login,
                "account_age_days": _parse_date(data.get("created_at")),
                "public_repos": data.get("public_repos", 0),
                "followers": data.get("followers", 0),
                "recent_push_days": recent,
                "url": data.get("html_url"),
            }
    except Exception:
        return {"status": "unavailable", "login": login}


async def devpost_evidence(username: str | None) -> dict:
    if not username:
        return {"status": "not_provided"}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://devpost.com/software/search",
                params={"query": username},
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
        projects = data.get("software", data.get("projects", []))
        if isinstance(projects, dict):
            projects = projects.get("software", [])
        matched = [
            p
            for p in projects
            if username.casefold()
            in str(p.get("members", "")).casefold()
        ]
        return {
            "status": "live",
            "projects": len(matched),
            "wins": sum(bool(p.get("winner")) for p in matched),
            "sample": [
                {"name": p.get("name", ""), "url": p.get("url", "")}
                for p in matched[:3]
            ],
        }
    except Exception:
        return {"status": "unavailable", "projects": 0, "wins": 0, "sample": []}


async def stopforumspam_evidence(email: str | None, username: str | None) -> dict:
    if not email and not username:
        return {"status": "not_provided", "email_appears": False, "username_appears": False, "confidence": 0}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                "https://api.stopforumspam.org/api",
                params={"json": None, "email": email or "", "username": username or ""},
            )
            response.raise_for_status()
            data = response.json()
        email_data = data.get("email", {})
        username_data = data.get("username", {})
        return {
            "status": "live",
            "email_appears": bool(email_data.get("appears")),
            "username_appears": bool(username_data.get("appears")),
            "confidence": max(
                float(email_data.get("confidence", 0) or 0),
                float(username_data.get("confidence", 0) or 0),
            ),
        }
    except Exception:
        return {
            "status": "unavailable",
            "email_appears": False,
            "username_appears": False,
            "confidence": 0,
        }


async def gather_evidence(applicant: dict, fixture: dict | None = None) -> dict:
    if fixture:
        return {
            "github": fixture.get("github", {"status": "simulated"}),
            "devpost": fixture.get("devpost", {"status": "simulated"}),
            "stopforumspam": fixture.get(
                "stopforumspam",
                {
                    "status": "simulated",
                    "email_appears": False,
                    "username_appears": False,
                    "confidence": 0,
                },
            ),
        }
    gh, dp, sfs = await asyncio.gather(
        github_evidence(applicant.get("github")),
        devpost_evidence(applicant.get("devpost")),
        stopforumspam_evidence(applicant.get("email"), applicant.get("chat_handle")),
    )
    return {"github": gh, "devpost": dp, "stopforumspam": sfs}
