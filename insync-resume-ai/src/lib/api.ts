// API client for the insync-backend FastAPI service.

import type {
  EmailCaptureResponse,
  JobSummary,
  LeadsRequestResponse,
  Metro,
  SampleDataResponse,
  ScoreProgressEvent,
  ScoreResponse,
} from "./api-types";
import { streamSSE } from "./sse-fetch";

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000";

function url(path: string): string {
  return `${API_BASE.replace(/\/+$/, "")}${path}`;
}

// ----- POST /api/score (SSE) -----------------------------------------------

export type ScoreCallbacks = {
  onProgress?: (e: ScoreProgressEvent) => void;
  signal?: AbortSignal;
};

export type ScoreInput = {
  jobDescription: string;
  resumes: File[];
  sessionId: string;
  prospectId?: string | null;
};

export async function scoreResumesStreaming(
  input: ScoreInput,
  callbacks: ScoreCallbacks = {},
): Promise<ScoreResponse> {
  const fd = new FormData();
  fd.append("job_description", input.jobDescription);
  fd.append("session_id", input.sessionId);
  if (input.prospectId) fd.append("prospect_id", input.prospectId);
  for (const f of input.resumes) fd.append("resumes", f, f.name);

  const stream = streamSSE(
    url("/api/score"),
    { method: "POST", body: fd, headers: { Accept: "text/event-stream" } },
    callbacks.signal,
  );

  let result: ScoreResponse | null = null;
  for await (const ev of stream) {
    if (ev.event === "progress") {
      try {
        callbacks.onProgress?.(JSON.parse(ev.data) as ScoreProgressEvent);
      } catch {
        // ignore malformed progress
      }
    } else if (ev.event === "result") {
      result = JSON.parse(ev.data) as ScoreResponse;
    } else if (ev.event === "error") {
      let msg = "Scoring failed.";
      try {
        msg = (JSON.parse(ev.data) as { message?: string }).message ?? msg;
      } catch {
        // ignore JSON parse error; use default
      }
      throw new Error(msg);
    }
  }

  if (!result) throw new Error("Scoring stream ended without a result.");
  return result;
}

// ----- GET /api/sample-data ------------------------------------------------

export async function fetchSampleData(): Promise<SampleDataResponse> {
  const r = await fetch(url("/api/sample-data"));
  if (!r.ok) throw new Error(`Sample data failed: HTTP ${r.status}`);
  return (await r.json()) as SampleDataResponse;
}

// ----- POST /api/capture/email --------------------------------------------

export type EmailCaptureInput = {
  email: string;
  sessionId: string;
  prospectId?: string | null;
  jobSummary: JobSummary;
  topCandidates: ScoreResponse["candidates"];
};

export async function captureEmail(input: EmailCaptureInput): Promise<EmailCaptureResponse> {
  const r = await fetch(url("/api/capture/email"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: input.email,
      session_id: input.sessionId,
      prospect_id: input.prospectId ?? null,
      job_summary: input.jobSummary,
      top_candidates: input.topCandidates.slice(0, 5),
    }),
  });
  if (!r.ok) throw new Error(await readErr(r));
  return (await r.json()) as EmailCaptureResponse;
}

// ----- POST /api/capture/leads-request ------------------------------------

export type LeadsRequestInput = {
  email: string;
  companyName: string;
  metro: Metro;
  roleFocus: string[];
  sessionId: string;
  prospectId?: string | null;
};

export async function requestLeads(input: LeadsRequestInput): Promise<LeadsRequestResponse> {
  const r = await fetch(url("/api/capture/leads-request"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: input.email,
      company_name: input.companyName,
      metro: input.metro,
      role_focus: input.roleFocus,
      session_id: input.sessionId,
      prospect_id: input.prospectId ?? null,
    }),
  });
  if (!r.ok) throw new Error(await readErr(r));
  return (await r.json()) as LeadsRequestResponse;
}

// ----- helpers -------------------------------------------------------------

async function readErr(r: Response): Promise<string> {
  const t = await r.text().catch(() => "");
  return `HTTP ${r.status}: ${t.slice(0, 300) || r.statusText}`;
}

// ----- client-side CSV (no backend round-trip) -----------------------------

export function candidatesToCsv(candidates: ScoreResponse["candidates"]): string {
  const headers = [
    "rank",
    "name",
    "score",
    "score_band",
    "one_line_summary",
    "candidate_location",
    "distance_miles",
    "commute_risk",
    "years_relevant",
    "matches_requirement",
    "strengths",
    "gaps",
    "interview_questions",
  ];
  const escape = (v: unknown): string => {
    const s = v == null ? "" : String(v);
    if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
    return s;
  };
  const lines = [headers.join(",")];
  candidates.forEach((c, i) => {
    lines.push(
      [
        i + 1,
        c.name,
        c.score,
        c.score_band,
        c.one_line_summary,
        c.location_match?.candidate_location ?? "",
        c.location_match?.distance_estimate_miles ?? "",
        c.location_match?.commute_risk ?? "",
        c.experience_match.years_relevant,
        c.experience_match.matches_requirement,
        c.strengths.join(" | "),
        c.gaps.join(" | "),
        c.interview_questions.join(" | "),
      ]
        .map(escape)
        .join(","),
    );
  });
  return lines.join("\n");
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url_ = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url_;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url_);
}
