# Insync Recruitment — AI Resume Screener

Free public B2B tool: scores resumes against a job description for logistics recruitment agencies. Drop a JD, upload up to 100 resumes, get ranked candidates in ~30 seconds.

## Repo layout

```
insync-resume-parser/
├── insync-backend/      Python · FastAPI · LangGraph · OpenAI · LlamaParse · Supabase
└── insync-resume-ai/    TypeScript · TanStack Start · React 19 · Tailwind v4 · Cloudflare Workers
```

Each subdirectory has its own `README.md` with setup, test, and deploy instructions.

## Architecture at a glance

- **Frontend** (`insync-resume-ai/`) — single-page TanStack Start app on Cloudflare Workers. Calls the backend via `fetch` + SSE for streaming scoring progress.
- **Backend** (`insync-backend/`) — FastAPI service. The scoring engine is a LangGraph workflow that fans out per-resume to parallel parse-and-score nodes, then aggregates + validates. Persists sessions and candidate scores to Supabase. Posts hot-lead alerts to Slack and emails results via Resend.

## Local dev

```sh
# 1. Backend
cd insync-backend
cp .env.example .env   # fill in OpenAI / LlamaParse / Supabase / Resend / Slack
uv sync
docker compose up -d redis
uv run uvicorn src.main:app --reload --port 8000

# 2. Frontend (separate terminal)
cd insync-resume-ai
bun install
bun run dev   # http://localhost:8080
```

## Tests

```sh
cd insync-backend
uv run pytest tests/unit -q                         # 26 unit tests
QUALITY_TESTS=1 uv run pytest tests/quality -q      # real-OpenAI quality gates (~$1)

cd insync-resume-ai
bun run lint
bunx tsc --noEmit
```

## Deploy

- **Backend** → Railway (Dockerfile + `railway.toml` ready). See `insync-backend/README.md` for the step-by-step.
- **Frontend** → Cloudflare Workers via `wrangler deploy` (TanStack Start handles the bundling). Set `VITE_API_BASE_URL` to the deployed backend URL.

## Status

All 7 build phases complete:

1. ✅ Skeleton & contract — Pydantic schemas + stubbed routes + Supabase DDL
2. ✅ Scoring engine — LangGraph + OpenAI + LlamaParse + Redis cache + SSE streaming
3. ✅ Quality harness — synthetic 5×10 corpus + consistency gate (`±5pt` variance)
4. ✅ Persistence + lead capture — Supabase repositories + Resend HTML/PDF + Slack
5. ✅ Hardening — slowapi rate limits + magic-bytes validation + cost telemetry
6. ✅ Deploy artifacts — `Dockerfile`, `docker-compose.yml`, `railway.toml`
7. ✅ Frontend wiring — real `fetch` + SSE + session tracking + 4 CTAs

**Quality bar:** consistency hard-gate passes (scoring same input × 3 stays within 5 points). Band-accuracy + top-pick are logged as soft gates — synthetic-corpus labels are noisy by design; **replacing them with 50 real hand-labeled resumes is the #1 post-launch must-do before promoting the tool to recruiters**.
