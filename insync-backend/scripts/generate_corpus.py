"""One-time corpus generator for the quality harness.

Generates 5 logistics JDs and 50 synthetic resumes (10 per JD: 4 strong, 3
moderate, 3 weak), saving them as plain text under tests/fixtures/. Also
writes tests/fixtures/manifest.json mapping each resume to its intended band
so the quality tests have ground truth.

Cost: ~$0.05-0.10 against gpt-4o-mini. Idempotent — re-running rewrites all
fixtures (commit them once you're happy).

    uv run python scripts/generate_corpus.py
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.llm.client import chat_json  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
JDS_DIR = FIXTURES / "jds"
RESUMES_DIR = FIXTURES / "resumes"


JD_BRIEFS: list[dict[str, str]] = [
    {
        "slug": "forklift_atlanta",
        "role": "Forklift Operator",
        "city": "Atlanta, GA",
        "context": "240,000 sq ft cross-dock facility, 10-hour shifts, $22-26/hr",
        "must_haves": "3+ years forklift, OSHA Class I/IV/V, reach truck AND counterbalance, WMS experience",
    },
    {
        "slug": "warehouse_dallas",
        "role": "Warehouse Associate",
        "city": "Dallas, TX",
        "context": "regional distribution center, picking and packing, RF scanner work, $18-22/hr",
        "must_haves": "1+ year warehouse, comfortable lifting 50 lbs, RF scanner experience, basic computer skills",
    },
    {
        "slug": "cdl_driver_columbus",
        "role": "CDL-A Driver",
        "city": "Columbus, OH",
        "context": "regional dedicated route, home weekly, $1,400-1,700/week",
        "must_haves": "Class A CDL, 1+ year OTR or regional, clean MVR (no DUI in last 7 years), DOT medical card",
    },
    {
        "slug": "picker_packer_phoenix",
        "role": "Picker/Packer",
        "city": "Phoenix, AZ",
        "context": "e-commerce fulfillment center, night shift, $17-19/hr",
        "must_haves": "fast-paced warehouse experience, comfortable standing 8 hours, ability to lift 40 lbs, attention to detail",
    },
    {
        "slug": "dock_worker_charlotte",
        "role": "Dock Worker",
        "city": "Charlotte, NC",
        "context": "LTL terminal, freight loading and unloading, early morning shift, $20-24/hr",
        "must_haves": "1+ year freight or dock experience, forklift certification, ability to lift 75 lbs repeatedly",
    },
]


JD_SYSTEM = """You are a logistics recruiter writing a real job posting. Output ONLY valid JSON:
{"jd": "the full job description as one string with line breaks"}

Write 200-350 words. Include:
- 1-line title with location and pay range
- 2-3 sentences about the company/site
- A bulleted requirements section with must-haves
- A bulleted "nice to have" section
- Schedule details

Tone: direct, blue-collar, no corporate fluff. Read like a real Indeed posting."""


RESUME_SYSTEM_TEMPLATE = """You are generating a synthetic resume for testing an AI resume scorer.

This resume must be a {band} match for the following job:

ROLE: {role}
LOCATION: {city}
MUST-HAVES: {must_haves}

Band definitions:
- "strong": clearly exceeds all must-haves, recent relevant experience, in/near the metro, has preferred extras
- "moderate": meets most must-haves with 1-2 gaps, related but not perfect experience, may be slightly out of area
- "weak": clearly wrong field OR missing 2+ must-haves; e.g. a barista applying for forklift, or an OOO candidate with no certs

Output ONLY valid JSON:
{{"name": "First Last", "resume_text": "the full resume text"}}

The resume text should be 200-400 words, plain text formatted like a real resume (Name + location header, then sections: Summary, Experience with dates, Certifications, Skills, Education). Use varied job histories and realistic employer names. Do NOT label the band in the text. Each candidate should feel distinct — varied names, ages, employers, formatting quirks."""


BANDS_PER_JD: list[str] = (
    ["strong"] * 4 + ["moderate"] * 3 + ["weak"] * 3
)  # 10 per JD = 50 total


async def generate_jd(brief: dict[str, str]) -> dict[str, str]:
    user_prompt = (
        f"ROLE: {brief['role']}\n"
        f"LOCATION: {brief['city']}\n"
        f"CONTEXT: {brief['context']}\n"
        f"MUST-HAVES: {brief['must_haves']}\n\n"
        f"Write the JD now."
    )
    call = await chat_json(
        model="gpt-4o-mini",
        system=JD_SYSTEM,
        user=user_prompt,
        temperature=0.4,
        max_tokens=800,
    )
    jd_text = call.parsed.get("jd", "").strip()
    return {"slug": brief["slug"], "jd_text": jd_text, "cost": call.cost}


async def generate_resume(
    jd_brief: dict[str, str], band: str, variant_idx: int
) -> dict[str, str]:
    system = RESUME_SYSTEM_TEMPLATE.format(
        band=band, role=jd_brief["role"], city=jd_brief["city"], must_haves=jd_brief["must_haves"]
    )
    user = (
        f"Generate variant #{variant_idx + 1} of a {band} candidate. Pick a name and "
        f"employment history NOT seen in your previous outputs in this conversation."
    )
    call = await chat_json(
        model="gpt-4o-mini",
        system=system,
        user=user,
        temperature=0.7,
        max_tokens=1000,
    )
    name = (call.parsed.get("name") or f"Candidate {variant_idx + 1}").strip()
    resume_text = (call.parsed.get("resume_text") or "").strip()
    return {
        "name": name,
        "resume_text": resume_text,
        "band": band,
        "cost": call.cost,
    }


def _slugify_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return s or "candidate"


async def main() -> int:
    JDS_DIR.mkdir(parents=True, exist_ok=True)
    RESUMES_DIR.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, dict] = {"jds": {}, "resumes": []}
    total_cost = 0.0
    t0 = time.perf_counter()

    # Stage 1: generate JDs in parallel
    print(f"Generating {len(JD_BRIEFS)} JDs...")
    jds = await asyncio.gather(*(generate_jd(b) for b in JD_BRIEFS))
    for jd, brief in zip(jds, JD_BRIEFS, strict=True):
        path = JDS_DIR / f"{jd['slug']}.txt"
        path.write_text(jd["jd_text"], encoding="utf-8")
        manifest["jds"][jd["slug"]] = {
            "role": brief["role"],
            "city": brief["city"],
            "path": str(path.relative_to(FIXTURES)),
        }
        total_cost += jd["cost"]
        print(f"  + {path.relative_to(ROOT)} ({len(jd['jd_text'])} chars)")

    # Stage 2: generate resumes per JD (in parallel within a JD, sequential across)
    for brief in JD_BRIEFS:
        slug = brief["slug"]
        out_dir = RESUMES_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"\nGenerating {len(BANDS_PER_JD)} resumes for {slug}...")
        resumes = await asyncio.gather(
            *(generate_resume(brief, band, i) for i, band in enumerate(BANDS_PER_JD))
        )
        for i, r in enumerate(resumes):
            filename = f"{r['band']}_{i:02d}_{_slugify_name(r['name'])}.txt"
            path = out_dir / filename
            path.write_text(r["resume_text"], encoding="utf-8")
            manifest["resumes"].append(
                {
                    "jd_slug": slug,
                    "name": r["name"],
                    "intended_band": r["band"],
                    "path": str(path.relative_to(FIXTURES)),
                }
            )
            total_cost += r["cost"]
            print(f"  + {path.name}  ({r['band']:8s}  {r['name']})")

    # Stage 3: write manifest
    (FIXTURES / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )

    elapsed = time.perf_counter() - t0
    print(
        f"\nDone. {len(jds)} JDs + {len(manifest['resumes'])} resumes in {elapsed:.1f}s "
        f"for ${total_cost:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
