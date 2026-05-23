"""GET /api/sample-data — fixed sample JD + 5 sample resumes for demo button."""

from __future__ import annotations

from fastapi import APIRouter, Request

from src.schemas.capture import SampleDataResponse, SampleResume
from src.services.limiter import get_limiter

router = APIRouter(prefix="/api", tags=["sample"])
_limiter = get_limiter()


SAMPLE_JD = """Forklift Operator — Atlanta, GA
Atlas Distribution Center | Full-time | $22–$26/hr

We're hiring an experienced forklift operator for our 240,000 sq ft cross-dock facility in Atlanta. You'll move freight between inbound trailers, staging lanes, and outbound docks during a 10-hour shift.

Requirements:
- 3+ years of forklift operation in a high-volume warehouse
- OSHA forklift certification (Class I, IV, or V)
- Comfortable with stand-up reach trucks AND sit-down counterbalance
- Experience with a WMS (Manhattan, HighJump, or similar)
- Able to lift 50 lbs and stand for 10-hour shifts
- Clean driving record; CDL is a plus

Nice to have:
- Cross-dock or 3PL background
- RF scanner experience
- Bilingual (English/Spanish)

Schedule: Sun–Wed, 6am–4:30pm. Within 25 miles of Atlanta preferred."""


SAMPLE_RESUMES: list[SampleResume] = [
    SampleResume(
        name="Marcus Williams",
        expected_score_band="strong",
        content=(
            "Marcus Williams\nAtlanta, GA\n\n"
            "Forklift Operator with 8 years of cross-dock experience. OSHA Class I, IV, V certified.\n"
            "Manhattan WMS daily user. CDL Class A. RF scanner expert. Bilingual EN/ES.\n"
            "Atlas Logistics (2018–present) — Lead Forklift Operator, 10-hour shifts.\n"
            "Premier 3PL (2016–2018) — Reach truck + counterbalance operator.\n"
        ),
    ),
    SampleResume(
        name="Sarah Johnson",
        expected_score_band="strong",
        content=(
            "Sarah Johnson\nMarietta, GA (18 mi from Atlanta)\n\n"
            "6 years forklift / warehouse operations. OSHA Class I & IV. HighJump WMS user.\n"
            "Reach truck certified. RF scanner experience. Stand-up + sit-down.\n"
            "Coast Distribution (2019–present) — Day shift forklift operator.\n"
        ),
    ),
    SampleResume(
        name="Derek Chen",
        expected_score_band="moderate",
        content=(
            "Derek Chen\nAtlanta, GA\n\n"
            "3 years warehouse associate. OSHA Class I certified one year ago.\n"
            "Sit-down counterbalance only; no reach truck. No WMS experience listed.\n"
            "RegionalWarehouse Co (2022–present) — Picker/packer with occasional forklift.\n"
        ),
    ),
    SampleResume(
        name="Tasha Roberts",
        expected_score_band="moderate",
        content=(
            "Tasha Roberts\nAthens, GA (60 mi from Atlanta)\n\n"
            "5 years forklift, last role 2 years ago. OSHA expired. SAP WMS user.\n"
            "Counterbalance forklift; some reach truck training.\n"
            "Athens Goods (2019–2023) — Day shift forklift operator.\n"
        ),
    ),
    SampleResume(
        name="Jamie Park",
        expected_score_band="weak",
        content=(
            "Jamie Park\nAtlanta, GA\n\n"
            "8 years retail customer service. Currently a barista.\n"
            "No forklift experience. No warehouse experience. No certifications.\n"
            "Looking for a career change into logistics.\n"
        ),
    ),
]


@router.get("/sample-data", response_model=SampleDataResponse)
@_limiter.limit("30/hour")
async def sample_data(request: Request) -> SampleDataResponse:
    return SampleDataResponse(job_description=SAMPLE_JD, sample_resumes=SAMPLE_RESUMES)
