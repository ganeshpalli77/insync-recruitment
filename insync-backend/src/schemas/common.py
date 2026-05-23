from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class APIModel(BaseModel):
    """Base for every wire model: forbid unknown fields on input, serialize cleanly."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


ScoreBand = Literal["strong", "moderate", "weak"]
CommuteRisk = Literal["low", "medium", "high", "unknown"]
ShiftType = Literal["day", "night", "rotating", "flexible", "unspecified"]
LeadStatus = Literal["new", "contacted", "converted", "rejected"]
ProspectStatus = Literal["cold", "tool_user", "engaged", "hot_lead", "converted"]


class ErrorResponse(APIModel):
    error: str
    detail: str | None = None
    code: str | None = None


class HealthResponse(APIModel):
    status: Literal["ok", "degraded", "down"]
    services: dict[str, str]
    version: str
    uptime_seconds: int


class JobSummary(APIModel):
    title: str
    location: str
    company: str | None = None
    required_experience_years: int | None = None
    required_certifications: list[str] = Field(default_factory=list)
    key_skills: list[str] = Field(default_factory=list)


class ParsedJD(APIModel):
    """Internal — full structured JD from parse_job_description node."""

    title: str
    location: str
    company: str | None = None
    required_experience_years: int | None = None
    required_certifications: list[str] = Field(default_factory=list)
    preferred_certifications: list[str] = Field(default_factory=list)
    key_skills: list[str] = Field(default_factory=list)
    physical_requirements: list[str] = Field(default_factory=list)
    shift_type: ShiftType = "unspecified"
    salary_range: str | None = None
    must_have_keywords: list[str] = Field(default_factory=list)
    nice_to_have_keywords: list[str] = Field(default_factory=list)


class TimestampedEvent(APIModel):
    timestamp: datetime
