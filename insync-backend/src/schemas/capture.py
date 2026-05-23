from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import EmailStr, Field

from .common import APIModel, JobSummary
from .score import CandidateScore


class EmailCaptureRequest(APIModel):
    email: EmailStr
    session_id: str
    prospect_id: str | None = None
    job_summary: JobSummary
    top_candidates: list[CandidateScore] = Field(max_length=5)


class EmailCaptureResponse(APIModel):
    success: bool
    message: str


Metro = Literal["atlanta", "dfw", "columbus", "other"]


class LeadsRequestBody(APIModel):
    email: EmailStr
    company_name: str
    metro: Metro
    role_focus: list[str] = Field(min_length=1)
    session_id: str
    prospect_id: str | None = None


class LeadsRequestResponse(APIModel):
    success: bool
    next_steps_message: str


# Sample data ---------------------------------------------------------------


class SampleResume(APIModel):
    name: str
    content: str
    expected_score_band: str


class SampleDataResponse(APIModel):
    job_description: str
    sample_resumes: list[SampleResume]


# Internal Track B webhook --------------------------------------------------

TrackBEventType = Literal[
    "tool_used", "exported_csv", "exported_pdf", "email_captured", "leads_requested"
]


class TrackBEvent(APIModel):
    prospect_id: str
    event_type: TrackBEventType
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime


class TrackBEventResponse(APIModel):
    success: bool
    event_id: str | None = None
