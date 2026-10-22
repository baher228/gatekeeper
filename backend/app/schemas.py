from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["accepted", "ask", "declined", "waitlisted"]
ReasonCategory = Literal["skill_gap", "minor_issue", "capacity", "scam_abuse", "rules_mismatch"]


class Rule(BaseModel):
    id: str | None = None
    text: str


class CategoryQuota(BaseModel):
    slug: str
    name: str
    quota: int
    bypass_quota: bool = False
    used: int = 0
    remaining: int = 0
    waitlisted: int = 0


class ApplyIn(BaseModel):
    name: str
    email: str
    phone: str | None = None
    github: str | None = None
    devpost: str | None = None
    chat_handle: str | None = None
    what_build: str
    category: str


class ApplicantSummary(BaseModel):
    id: str
    name: str
    category: str
    status: Status
    final_score: float
    confidence: float
    top_reason: str
    decision_source: Literal["auto", "lead"]
    created_at: datetime
    is_seed: bool
    reconsidered: bool = False


class ApplicantDetail(ApplicantSummary):
    community_slug: str
    email: str
    phone_masked: str | None = None
    github: str | None = None
    devpost: str | None = None
    chat_handle: str | None = None
    what_build: str
    decided_at: datetime | None = None
    decline_reason: ReasonCategory | None = None
    recommendation: dict
    reconsideration: dict
    decisions: list[dict] = Field(default_factory=list)


class DecisionIn(BaseModel):
    verdict: Literal["accept", "ask_more", "decline"]
    reason_category: ReasonCategory | None = None
    note: str | None = None


class ModelInfo(BaseModel):
    available: bool
    n_decisions: int
    n_accept: int
    n_decline: int
    trained_at: datetime | None = None
    coefficients: list[dict] = Field(default_factory=list)


class BlocklistIn(BaseModel):
    identifier_type: Literal["phone", "email", "github", "handle"]
    identifier: str
    evidence: str
    links: list[str] = Field(default_factory=list)


class AppealIn(BaseModel):
    identifier_type: Literal["phone", "email", "github", "handle"]
    identifier: str
    contact: str
    message: str


class ResolveAppealIn(BaseModel):
    outcome: Literal["upheld", "rejected"]


class SettingsIn(BaseModel):
    rules: list[Rule]
    categories: list[CategoryQuota]
    reconsider_cooldown_days: int = 60
