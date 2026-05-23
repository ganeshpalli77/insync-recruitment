// Local fallback constants. Real data flows from the backend at runtime:
//   - JD sample → GET /api/sample-data
//   - Candidate results → POST /api/score (SSE)
// Kept here so the UI has reasonable defaults if the API is unreachable
// (e.g., during offline frontend development).

export const SAMPLE_JD = `Forklift Operator — Atlanta, GA
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

Schedule: Sun–Wed, 6am–4:30pm. Within 25 miles of Atlanta preferred.`;
