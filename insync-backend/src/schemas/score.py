from __future__ import annotations

from pydantic import Field

from .common import APIModel, CommuteRisk, JobSummary, ScoreBand


class LocationMatch(APIModel):
    candidate_location: str | None = None
    distance_estimate_miles: int | None = None
    commute_risk: CommuteRisk = "unknown"


class ExperienceMatch(APIModel):
    years_relevant: float
    matches_requirement: bool
    notes: str


class CandidateScore(APIModel):
    candidate_id: str
    name: str
    score: int = Field(ge=0, le=100)
    score_band: ScoreBand
    one_line_summary: str
    strengths: list[str] = Field(min_length=1)
    gaps: list[str] = Field(min_length=1)
    interview_questions: list[str] = Field(min_length=1)
    location_match: LocationMatch | None = None
    experience_match: ExperienceMatch
    raw_resume_text: str


class ScoringMetadata(APIModel):
    processing_time_ms: int
    model_parser: str
    model_scorer: str
    total_tokens_used: int = 0
    total_cost_usd: float = 0.0
    cache_hit: bool = False
    failed_resume_count: int = 0


class ScoreResponse(APIModel):
    job_summary: JobSummary
    candidates: list[CandidateScore]
    metadata: ScoringMetadata
    session_id: str
    # True when the prospect already gave us name+email+company on a prior
    # visit. The frontend uses this to skip the email gate on returning users.
    # Defaults False so cached pre-Phase-8 responses fall through to the gate.
    lead_registered: bool = False


# SSE event payloads ---------------------------------------------------------


class ScoreProgressEvent(APIModel):
    event: str = "progress"
    completed: int
    total: int
    candidate_name: str | None = None


class ScoreResultEvent(APIModel):
    event: str = "result"
    data: ScoreResponse


class ScoreErrorEvent(APIModel):
    event: str = "error"
    message: str
    code: str | None = None
