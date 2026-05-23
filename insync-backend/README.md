# Insync Recruitment — AI Resume Screener (backend)

Free public B2B tool: scores resumes against a job description for logistics recruitment agencies.

## Stack

FastAPI + LangGraph + OpenAI + LlamaParse + Supabase + Redis. Python 3.11+, managed by [uv](https://docs.astral.sh/uv/).

## Rate limits & free-tier caps

Per the spec, free-tier limits are enforced on every endpoint:

- `POST /api/score` — 5/hour/IP
- `POST /api/capture/*` — 3/hour/IP
- `GET /api/sample-data` — 30/hour/IP
- Daily cap of 100 resumes per IP (regardless of how they're spread across requests)
- Daily cost alert when 24h OpenAI spend crosses `DAILY_COST_ALERT_USD`

`RATE_LIMIT_STORAGE` defaults to `memory://` (single-instance, fine for Railway 1-replica). Set to `redis://...` to share counters across replicas.

## Local development

```sh
# 1. Install deps (creates .venv)
uv sync

# 2. Configure
cp .env.example .env
# Fill in OPENAI_API_KEY, LLAMA_CLOUD_API_KEY, SUPABASE_*, RESEND_API_KEY.

# 3. Start Redis + a mock CRM receiver
docker compose up -d redis mock-crm

# 4. Run the API
uv run uvicorn src.main:app --reload

# Visit OpenAPI docs at http://localhost:8000/docs
```

### Tests

```sh
uv run pytest tests/unit -v
uv run pytest tests/integration -v          # needs real Supabase/OpenAI keys
QUALITY_TESTS=1 uv run pytest tests/quality -v   # expensive (~$5)
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET  | `/health` | Liveness + dependency status. |
| POST | `/api/score` | Score N resumes against a JD. SSE stream by default; pass `?stream=false` for JSON. |
| POST | `/api/capture/email` | Email a copy of the results to the user. |
| POST | `/api/capture/leads-request` | "Show me leads" hot-lead form. |
| GET  | `/api/sample-data` | Pre-built sample JD + 5 sample resumes for the demo button. |
| POST | `/api/webhook/track-b-trigger` | Internal — prospect events → CRM + Slack. |

Auto-generated OpenAPI docs at `/docs`.

## Supabase

The schema lives in `MIGRATION.sql`. Apply it once against a fresh project:

```sh
psql "$SUPABASE_DB_URL" -f MIGRATION.sql
```

Or, from a Claude Code session with the Supabase MCP enabled, apply each statement via `apply_migration` with per-step confirmation.

## Deployment

A multi-stage `Dockerfile` produces a slim runtime image with WeasyPrint's native deps installed. Works on Railway, Render, or Fly. `WEB_CONCURRENCY` (default 2) controls Uvicorn workers; `PORT` (default 8000) is honored.

### Deploy to Railway (recommended)

1. **Push to a Git repo** (GitHub/GitLab). The repo root or a subdirectory containing this `insync-backend/` folder both work; if it's a subdirectory, set Railway's "Root Directory" to `insync-backend` after step 4.
2. **Sign in** to [railway.app](https://railway.app) and click **New Project** → **Deploy from GitHub repo** → pick your repo.
3. **Add a Redis plugin** to the project: in the project dashboard click **+ New** → **Database** → **Redis**. Railway auto-creates a `REDIS_URL` reference variable.
4. **Set env vars** on the API service (Settings → Variables). Copy from `.env` but **omit the placeholder ones** and reference Redis explicitly:
   ```
   OPENAI_API_KEY=sk-...
   OPENAI_MODEL_PARSER=gpt-4o-mini
   OPENAI_MODEL_SCORER=gpt-4o
   LLAMA_CLOUD_API_KEY=llx-...
   SUPABASE_URL=https://hlzdlgspvlkrxvddhdqc.supabase.co
   SUPABASE_SERVICE_KEY=eyJ...        # from Supabase dashboard → Settings → API
   SUPABASE_ANON_KEY=sb_publishable_...
   REDIS_URL=${{Redis.REDIS_URL}}     # template ref, not a literal
   RATE_LIMIT_STORAGE=${{Redis.REDIS_URL}}
   RESEND_API_KEY=re_...               # optional
   SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...  # optional
   CRM_WEBHOOK_URL=                    # optional
   FRONTEND_URL=https://your-frontend.example.com
   ALLOWED_ORIGINS=https://your-frontend.example.com
   ENVIRONMENT=production
   DAILY_COST_ALERT_USD=50
   LOG_LEVEL=INFO
   ```
5. **Deploy**. Railway builds the Dockerfile, runs the baked `HEALTHCHECK`, and serves the API at `https://<project>.up.railway.app`.
6. **Smoke test**:
   ```sh
   curl https://<project>.up.railway.app/health        # 200 OK
   curl https://<project>.up.railway.app/api/sample-data | jq .job_description | head
   ```
7. **Wire the frontend**: set `VITE_API_BASE_URL=https://<project>.up.railway.app` in the frontend's environment (Cloudflare Workers `vars` in `wrangler.jsonc` for prod, `.env` for dev) and redeploy.
8. **Tighten CORS**: once the frontend is live, narrow `ALLOWED_ORIGINS` on Railway to your actual production domain — no `localhost`.

### Render or Fly

The Dockerfile is host-agnostic. On Render add a Redis "Key Value" service and reference its internal URL; on Fly use `fly mpg` or a Redis VM. Same env vars, same `/health` probe.

### Pre-deploy checklist

- [ ] `uv run pytest tests/unit` green
- [ ] `QUALITY_TESTS=1 uv run pytest tests/quality/test_consistency.py` green (hard gate)
- [ ] `.env` keys are in your hosting provider's secret store, not committed
- [ ] Supabase migrations applied (`MIGRATION.sql` or via MCP `apply_migration`)
- [ ] `ALLOWED_ORIGINS` set to your real frontend URL, not `*`
- [ ] `DAILY_COST_ALERT_USD` set to a number you're comfortable being paged at

## Build phases

1. **Skeleton & contract** — `MIGRATION.sql`, all Pydantic schemas, FastAPI app, 5 stubbed routes. Frontend can wire against the contract.
2. **Scoring engine** — LangGraph (parse_jd → fan-out parse_and_score → aggregate → quality_check), OpenAI + LlamaParse wrappers, SSE streaming, Redis cache.
3. **Quality harness** — synthetic corpus, consistency hard-gate (≤ 5pt variance), band/top-pick soft-gates.
4. **Persistence + lead capture** — Supabase repositories, Resend + jinja + WeasyPrint, Slack webhook.
5. **Hardening** — slowapi rate limits, file/input validation, cost alert, structured logging.
6. **Deploy** — Railway.
7. **Frontend wiring** — `insync-resume-ai/` updates to consume the live API.
