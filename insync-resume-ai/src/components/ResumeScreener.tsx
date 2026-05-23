import { useEffect, useMemo, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  ChevronDown,
  FileText,
  Plus,
  Upload,
  X,
  AlertTriangle,
  Check,
  Sparkles,
  Mail,
  Download,
  Rocket,
  ArrowRight,
  Loader2,
} from "lucide-react";
import { SAMPLE_JD } from "@/lib/mock-data";
import {
  candidatesToCsv,
  captureEmail,
  downloadCsv,
  fetchSampleData,
  requestLeads,
  scoreResumesStreaming,
} from "@/lib/api";
import type { CandidateScore, JobSummary, Metro, ScoreResponse } from "@/lib/api-types";

type Stage = "input" | "loading" | "results";

type UploadedFile = { file: File; name: string; size: number };

type Progress = { completed: number; total: number; currentName: string | null };

const ACCEPTED = [".pdf", ".docx", ".txt"];

function formatBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function scoreColor(score: number) {
  if (score >= 80)
    return {
      dot: "bg-emerald",
      text: "text-emerald",
      ring: "ring-emerald/30",
      glow: "shadow-[0_0_30px_-8px_var(--emerald)]",
    };
  if (score >= 60)
    return {
      dot: "bg-warn",
      text: "text-warn",
      ring: "ring-warn/30",
      glow: "shadow-[0_0_30px_-8px_var(--warn)]",
    };
  return {
    dot: "bg-danger",
    text: "text-danger",
    ring: "ring-danger/30",
    glow: "shadow-[0_0_30px_-8px_var(--danger)]",
  };
}

function useCountUp(target: number, duration = 600, start = true) {
  const [v, setV] = useState(0);
  useEffect(() => {
    if (!start) return;
    let raf = 0;
    const t0 = performance.now();
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / duration);
      const eased = 1 - Math.pow(1 - p, 3);
      setV(Math.round(target * eased));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration, start]);
  return v;
}

function makeSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function Header() {
  return (
    <header className="sticky top-0 z-50 h-[60px] border-b border-hairline bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex h-full max-w-6xl items-center justify-between px-5">
        <div className="flex items-center gap-2.5">
          <div className="leading-tight">
            <div className="text-sm font-bold tracking-tight text-foreground">Insync</div>
            <div className="text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Recruitment Tools
            </div>
          </div>
        </div>
        <div className="hidden sm:inline-flex items-center gap-2 rounded-full border border-emerald/20 bg-emerald/5 px-3 py-1.5 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald" />
          Built for logistics recruiters
        </div>
      </div>
    </header>
  );
}

function Hero() {
  const heading = "AI Resume Screener";
  return (
    <div className="relative pt-16 pb-10 text-center md:pt-24 md:pb-14">
      <h1 className="mx-auto max-w-4xl text-[36px] font-bold leading-[1.02] tracking-tight md:text-[56px]">
        {heading.split("").map((c, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.03, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="inline-block text-gradient-emerald"
          >
            {c === " " ? " " : c}
          </motion.span>
        ))}
      </h1>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4, duration: 0.6 }}
        className="mx-auto mt-5 max-w-[600px] px-4 text-[16px] leading-relaxed text-muted-foreground md:text-[18px]"
      >
        Built for logistics recruiters. Drop a job description. Upload resumes. Get ranked
        candidates in 30 seconds.
      </motion.p>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.7, duration: 0.6 }}
        className="mt-5 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-muted-foreground"
      >
        {["No signup", "Free forever", "Resumes never stored"].map((t) => (
          <span key={t} className="inline-flex items-center gap-1.5">
            <Check className="h-3.5 w-3.5 text-emerald" /> {t}
          </span>
        ))}
      </motion.div>
    </div>
  );
}

function JDCard({
  jd,
  setJd,
  onLoadSample,
  sampleLoading,
}: {
  jd: string;
  setJd: (s: string) => void;
  onLoadSample: () => void;
  sampleLoading: boolean;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);
  const words = jd.trim() ? jd.trim().split(/\s+/).length : 0;

  return (
    <div className="rounded-2xl border border-hairline bg-surface/60 p-5 backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald">
          Job Description
        </h3>
        <span className="text-[11px] text-muted-foreground">{words} words</span>
      </div>
      <div
        className={`relative rounded-xl border bg-background/60 transition-all duration-300 ${
          focused ? "border-emerald/40 ring-emerald-focus" : "border-hairline"
        }`}
      >
        <textarea
          value={jd}
          onChange={(e) => setJd(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          rows={10}
          placeholder="Paste the job description here, or use a sample to get started…"
          className="w-full resize-none rounded-xl bg-transparent p-4 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/60 focus:outline-none"
        />
      </div>
      <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5 text-emerald" /> Tip: more detail = better scoring
      </p>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          onClick={() => fileRef.current?.click()}
          className="rounded-lg border border-hairline bg-background/40 px-3 py-2 text-xs text-muted-foreground transition hover:border-emerald/30 hover:text-foreground"
        >
          Or upload JD as PDF/TXT
        </button>
        <button
          onClick={onLoadSample}
          disabled={sampleLoading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-emerald/20 bg-emerald/5 px-3 py-2 text-xs text-emerald transition hover:bg-emerald/10 disabled:opacity-50"
        >
          {sampleLoading && <Loader2 className="h-3 w-3 animate-spin" />}
          Use sample data
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.txt"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            // We don't parse the JD PDF on the client; read .txt as-is and
            // fall back to a labeled stub for PDFs (the user can paste).
            if (f.type === "text/plain" || f.name.toLowerCase().endsWith(".txt")) {
              f.text()
                .then(setJd)
                .catch(() => setJd(`[Loaded from ${f.name}]\n\n${SAMPLE_JD}`));
            } else {
              setJd(`[Loaded from ${f.name}]\n\n${SAMPLE_JD}`);
            }
          }}
        />
      </div>
    </div>
  );
}

function ResumesCard({
  files,
  setFiles,
}: {
  files: UploadedFile[];
  setFiles: (f: UploadedFile[]) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFiles = (list: FileList | File[]) => {
    setError(null);
    const arr = Array.from(list);
    const accepted: UploadedFile[] = [];
    const rejected: string[] = [];
    for (const f of arr) {
      const ext = "." + f.name.split(".").pop()?.toLowerCase();
      if (!ACCEPTED.includes(ext)) rejected.push(f.name);
      else accepted.push({ file: f, name: f.name, size: f.size });
    }
    const next = [...files, ...accepted].slice(0, 100);
    if (files.length + accepted.length > 100) {
      setError("Limit is 100 files. Extra files were ignored.");
    }
    if (rejected.length) {
      setError((e) => (e ? e + " " : "") + `Unsupported: ${rejected.join(", ")}`);
    }
    setFiles(next);
  };

  return (
    <div className="flex h-full flex-col rounded-2xl border border-hairline bg-surface/60 p-5 backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald">Resumes</h3>
        <span className="text-[11px] text-muted-foreground">{files.length} ready</span>
      </div>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          onFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`flex flex-1 min-h-[260px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed py-10 px-6 text-center transition-all ${
          dragging
            ? "border-emerald bg-emerald/5 ring-emerald-focus"
            : "border-emerald/25 bg-background/30 hover:border-emerald/50 hover:bg-emerald/[0.03]"
        }`}
      >
        <Upload className="mb-2 h-5 w-5 text-emerald" />
        <div className="text-sm font-medium text-foreground">Drop resumes here</div>
        <div className="text-xs text-muted-foreground">or click to browse</div>
        <div className="mt-3 text-[11px] text-muted-foreground">
          PDF, DOCX, or TXT • Up to 100 files
        </div>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.txt"
          className="hidden"
          onChange={(e) => e.target.files && onFiles(e.target.files)}
        />
      </div>

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-warn/30 bg-warn/5 px-3 py-2 text-xs text-warn">
          <AlertTriangle className="mt-[1px] h-3.5 w-3.5 shrink-0" /> {error}
        </div>
      )}

      {files.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-xs text-muted-foreground">Uploaded ({files.length}):</div>
          <ul className="space-y-1.5 max-h-48 overflow-auto scrollbar-thin pr-1">
            <AnimatePresence initial={false}>
              {files.map((f, i) => (
                <motion.li
                  key={f.name + i}
                  initial={{ opacity: 0, y: -6, scale: 0.97 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ type: "spring", stiffness: 380, damping: 26 }}
                  className="flex items-center justify-between gap-2 rounded-lg border border-hairline bg-background/40 px-3 py-2 text-xs"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-emerald" />
                    <span className="truncate text-foreground">{f.name}</span>
                    <span className="shrink-0 text-muted-foreground">· {formatBytes(f.size)}</span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setFiles(files.filter((_, j) => j !== i));
                    }}
                    className="rounded p-1 text-muted-foreground transition hover:bg-hairline hover:text-danger"
                    aria-label="Remove"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
          <button
            onClick={() => inputRef.current?.click()}
            className="mt-3 inline-flex items-center gap-1 text-xs text-emerald hover:text-mint transition"
          >
            <Plus className="h-3.5 w-3.5" /> Add more
          </button>
        </div>
      )}
    </div>
  );
}

function CandidateCard({
  c,
  defaultOpen,
  index,
}: {
  c: CandidateScore;
  defaultOpen: boolean;
  index: number;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const color = scoreColor(c.score);
  const v = useCountUp(c.score, 700);

  return (
    <motion.div
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="group rounded-2xl border border-hairline bg-surface/60 transition-all hover:-translate-y-0.5 hover:border-emerald/30 hover:shadow-[0_0_50px_-20px_var(--emerald)]"
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-4 p-5 text-left"
      >
        <div
          className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-background/60 ring-1 ${color.ring} ${color.glow}`}
        >
          <span className={`text-xl font-bold ${color.text}`}>{v}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${color.dot}`} />
            <h4 className="truncate text-base font-bold text-foreground md:text-lg">{c.name}</h4>
          </div>
          <p className="mt-0.5 truncate text-sm text-muted-foreground">{c.one_line_summary}</p>
        </div>
        <motion.div animate={{ rotate: open ? 180 : 0 }} className="shrink-0 text-muted-foreground">
          <ChevronDown className="h-5 w-5" />
        </motion.div>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="space-y-6 border-t border-hairline px-5 pb-6 pt-5">
              <section>
                <h5 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald">
                  Strengths
                </h5>
                <ul className="space-y-1.5">
                  {c.strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-foreground/90">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald" />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h5 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald">
                  Gaps
                </h5>
                <ul className="space-y-1.5">
                  {c.gaps.map((s, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-foreground/90">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
                      <span>{s}</span>
                    </li>
                  ))}
                </ul>
              </section>
              <section>
                <h5 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-emerald">
                  Suggested Interview Questions
                </h5>
                <ol className="space-y-1.5">
                  {c.interview_questions.map((q, i) => (
                    <li key={i} className="flex gap-2 text-sm text-muted-foreground">
                      <span className="text-emerald">{i + 1}.</span>
                      <span>{q}</span>
                    </li>
                  ))}
                </ol>
              </section>
              {c.experience_match && (
                <section className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-hairline bg-background/40 p-3 text-xs">
                    <div className="mb-1 text-muted-foreground">Relevant experience</div>
                    <div className="text-foreground">
                      {c.experience_match.years_relevant.toFixed(1)} yrs ·{" "}
                      {c.experience_match.matches_requirement ? (
                        <span className="text-emerald">meets requirement</span>
                      ) : (
                        <span className="text-warn">below requirement</span>
                      )}
                    </div>
                    <div className="mt-1 text-muted-foreground">{c.experience_match.notes}</div>
                  </div>
                  {c.location_match && (
                    <div className="rounded-lg border border-hairline bg-background/40 p-3 text-xs">
                      <div className="mb-1 text-muted-foreground">Location</div>
                      <div className="text-foreground">
                        {c.location_match.candidate_location ?? "Unknown"}
                        {c.location_match.distance_estimate_miles != null && (
                          <> · ~{c.location_match.distance_estimate_miles} mi</>
                        )}
                      </div>
                      <div className="mt-1 text-muted-foreground">
                        Commute risk:{" "}
                        <span className="text-foreground/80">{c.location_match.commute_risk}</span>
                      </div>
                    </div>
                  )}
                </section>
              )}
              {c.raw_resume_text && (
                <details className="text-xs text-muted-foreground">
                  <summary className="cursor-pointer text-emerald hover:text-mint">
                    View original resume (first 500 chars)
                  </summary>
                  <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded border border-hairline bg-background/50 p-3 font-mono">
                    {c.raw_resume_text}
                  </pre>
                </details>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function LoadingBlock({ progress }: { progress: Progress }) {
  const total = Math.max(progress.total, 1);
  const completed = Math.max(progress.completed, 0);
  // Show "X of N" — display 1-indexed for friendlier UX (resume #1 of 3).
  const displayIdx = Math.min(completed + 1, total);
  const pct = Math.min(100, (completed / total) * 100);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="mx-auto mt-2 max-w-md rounded-2xl border border-hairline bg-surface/60 p-8 text-center"
    >
      <div
        className="mx-auto mb-5 h-10 w-10 animate-pulse-glow rounded-full border-2 border-emerald/40 border-t-emerald"
        style={{ animation: "spin 1s linear infinite, pulse-glow 2.4s ease-in-out infinite" }}
      />
      <div className="text-base font-semibold text-foreground">Scoring candidates…</div>
      <div className="mt-2 text-sm text-muted-foreground">
        {progress.currentName
          ? `Just scored: ${progress.currentName}`
          : `Analyzing resume ${displayIdx} of ${total}`}
      </div>
      <div className="mx-auto mt-5 h-1.5 w-full overflow-hidden rounded-full bg-hairline">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-emerald-deep via-emerald to-mint"
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4, ease: "easeOut" }}
        />
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </motion.div>
  );
}

function EmailCaptureCard({
  response,
  sessionId,
  prospectId,
}: {
  response: ScoreResponse;
  sessionId: string;
  prospectId: string | null;
}) {
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [msg, setMsg] = useState<string | null>(null);

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        if (!email.trim()) return;
        setStatus("sending");
        setMsg(null);
        try {
          const r = await captureEmail({
            email: email.trim(),
            sessionId,
            prospectId,
            jobSummary: response.job_summary,
            topCandidates: response.candidates,
          });
          setStatus("sent");
          setMsg(r.message);
        } catch (err) {
          setStatus("error");
          setMsg(err instanceof Error ? err.message : "Send failed");
        }
      }}
      className="flex flex-col gap-2"
    >
      <div className="flex gap-2">
        <input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@agency.com"
          disabled={status === "sending" || status === "sent"}
          className="min-w-0 flex-1 rounded-lg border border-hairline bg-background/50 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald/40 focus:outline-none disabled:opacity-60"
        />
        <button
          disabled={status === "sending" || status === "sent"}
          className="inline-flex items-center gap-1 rounded-lg bg-emerald px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-mint disabled:opacity-60"
        >
          {status === "sending" ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
          {status === "sent" ? "Sent" : "Send"}{" "}
          {status !== "sending" && status !== "sent" && <ArrowRight className="h-3 w-3" />}
        </button>
      </div>
      {msg && (
        <p
          className={`text-[11px] ${status === "error" ? "text-danger" : "text-muted-foreground"}`}
        >
          {msg}
        </p>
      )}
    </form>
  );
}

function LeadsCard({ sessionId, prospectId }: { sessionId: string; prospectId: string | null }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [metro, setMetro] = useState<Metro>("atlanta");
  const [roles, setRoles] = useState<string>("forklift, warehouse");
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [msg, setMsg] = useState<string | null>(null);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1 rounded-lg bg-emerald px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-mint"
      >
        Show me leads <ArrowRight className="h-3 w-3" />
      </button>
    );
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setStatus("sending");
        setMsg(null);
        try {
          const r = await requestLeads({
            email: email.trim(),
            companyName: company.trim(),
            metro,
            roleFocus: roles
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
            sessionId,
            prospectId,
          });
          setStatus("sent");
          setMsg(r.next_steps_message);
        } catch (err) {
          setStatus("error");
          setMsg(err instanceof Error ? err.message : "Request failed");
        }
      }}
      className="space-y-2"
    >
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@agency.com"
        disabled={status === "sending" || status === "sent"}
        className="w-full rounded-lg border border-hairline bg-background/50 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald/40 focus:outline-none disabled:opacity-60"
      />
      <input
        type="text"
        required
        value={company}
        onChange={(e) => setCompany(e.target.value)}
        placeholder="Agency name"
        disabled={status === "sending" || status === "sent"}
        className="w-full rounded-lg border border-hairline bg-background/50 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald/40 focus:outline-none disabled:opacity-60"
      />
      <div className="flex gap-2">
        <select
          value={metro}
          onChange={(e) => setMetro(e.target.value as Metro)}
          disabled={status === "sending" || status === "sent"}
          className="flex-1 rounded-lg border border-hairline bg-background/50 px-3 py-2 text-xs text-foreground focus:border-emerald/40 focus:outline-none disabled:opacity-60"
        >
          <option value="atlanta">Atlanta</option>
          <option value="dfw">DFW</option>
          <option value="columbus">Columbus</option>
          <option value="other">Other</option>
        </select>
        <input
          type="text"
          value={roles}
          onChange={(e) => setRoles(e.target.value)}
          placeholder="forklift, cdl"
          disabled={status === "sending" || status === "sent"}
          className="flex-1 rounded-lg border border-hairline bg-background/50 px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-emerald/40 focus:outline-none disabled:opacity-60"
        />
      </div>
      <button
        disabled={status === "sending" || status === "sent"}
        className="inline-flex w-full items-center justify-center gap-1 rounded-lg bg-emerald px-3 py-2 text-xs font-semibold text-primary-foreground hover:bg-mint disabled:opacity-60"
      >
        {status === "sending" ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
        {status === "sent" ? "Requested" : "Request introductions"}
      </button>
      {msg && (
        <p
          className={`text-[11px] ${status === "error" ? "text-danger" : "text-muted-foreground"}`}
        >
          {msg}
        </p>
      )}
    </form>
  );
}

function HookCards({
  response,
  sessionId,
  prospectId,
  onDownloadCsv,
}: {
  response: ScoreResponse;
  sessionId: string;
  prospectId: string | null;
  onDownloadCsv: () => void;
}) {
  return (
    <div className="mt-12 grid gap-4 md:grid-cols-3">
      {[
        {
          icon: <Download className="h-5 w-5" />,
          title: "Save your results",
          body: "Download the ranking as a spreadsheet.",
          action: (
            <div className="flex gap-2">
              <button
                onClick={onDownloadCsv}
                className="rounded-lg border border-emerald/30 bg-emerald/5 px-3 py-2 text-xs font-medium text-emerald hover:bg-emerald/10"
              >
                Download CSV
              </button>
              <button
                disabled
                title="PDF export coming soon"
                className="rounded-lg border border-hairline px-3 py-2 text-xs text-muted-foreground/60"
              >
                Download PDF
              </button>
            </div>
          ),
        },
        {
          icon: <Mail className="h-5 w-5" />,
          title: "Email yourself a copy",
          body: "Get these results in your inbox.",
          action: (
            <EmailCaptureCard response={response} sessionId={sessionId} prospectId={prospectId} />
          ),
        },
        {
          icon: <Rocket className="h-5 w-5" />,
          title: "Need fresh hiring leads?",
          body: "We track 3,000+ logistics hiring posts daily.",
          action: <LeadsCard sessionId={sessionId} prospectId={prospectId} />,
        },
      ].map((card, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: i * 0.1, duration: 0.5 }}
          className="group relative rounded-2xl border border-hairline bg-surface/60 p-5 transition-all hover:-translate-y-1 hover:border-emerald/30 hover:shadow-[0_10px_60px_-20px_var(--emerald)]"
        >
          <div className="absolute inset-x-5 top-0 h-[3px] rounded-b-full bg-gradient-to-r from-emerald-deep via-emerald to-mint" />
          <div className="mb-3 inline-flex h-9 w-9 items-center justify-center rounded-lg bg-emerald/10 text-emerald">
            {card.icon}
          </div>
          <h4 className="text-sm font-bold text-foreground">{card.title}</h4>
          <p className="mt-1 mb-4 text-xs text-muted-foreground">{card.body}</p>
          {card.action}
        </motion.div>
      ))}
    </div>
  );
}

function CursorGlow() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (
      window.matchMedia("(hover: none)").matches ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    )
      return;
    let x = 0,
      y = 0,
      tx = 0,
      ty = 0,
      raf = 0;
    const onMove = (e: MouseEvent) => {
      tx = e.clientX;
      ty = e.clientY;
    };
    const loop = () => {
      x += (tx - x) * 0.08;
      y += (ty - y) * 0.08;
      if (ref.current) ref.current.style.transform = `translate3d(${x - 300}px, ${y - 300}px, 0)`;
      raf = requestAnimationFrame(loop);
    };
    window.addEventListener("mousemove", onMove);
    raf = requestAnimationFrame(loop);
    return () => {
      window.removeEventListener("mousemove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);
  return (
    <div
      ref={ref}
      aria-hidden
      className="pointer-events-none fixed left-0 top-0 z-0 h-[600px] w-[600px] rounded-full opacity-[0.08] blur-3xl"
      style={{ background: "radial-gradient(circle, var(--emerald) 0%, transparent 60%)" }}
    />
  );
}

export default function ResumeScreener({ prospectId }: { prospectId: string | null }) {
  const [jd, setJd] = useState("");
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [stage, setStage] = useState<Stage>("input");
  const [response, setResponse] = useState<ScoreResponse | null>(null);
  const [progress, setProgress] = useState<Progress>({ completed: 0, total: 0, currentName: null });
  const [scoreError, setScoreError] = useState<string | null>(null);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sortDesc, setSortDesc] = useState(true);
  const [filter, setFilter] = useState<"all" | "green" | "yellow" | "red">("all");
  const resultsRef = useRef<HTMLDivElement>(null);
  const [sessionId] = useState<string>(() => makeSessionId());

  const canSubmit = jd.trim().length >= 50 && files.length > 0;

  const onScore = async () => {
    if (!canSubmit) return;
    setScoreError(null);
    setStage("loading");
    setProgress({ completed: 0, total: files.length, currentName: null });
    setResponse(null);

    try {
      const result = await scoreResumesStreaming(
        {
          jobDescription: jd,
          resumes: files.map((f) => f.file),
          sessionId,
          prospectId,
        },
        {
          onProgress: (p) =>
            setProgress({
              completed: p.completed,
              total: p.total,
              currentName: p.candidate_name,
            }),
        },
      );
      setResponse(result);
      setStage("results");
      setTimeout(
        () => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }),
        200,
      );
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Scoring failed.";
      setScoreError(msg);
      setStage("input");
    }
  };

  const onLoadSample = async () => {
    setSampleLoading(true);
    try {
      const sample = await fetchSampleData();
      setJd(sample.job_description);
      // Wrap each sample resume's text in a virtual File so the user can
      // immediately click "Score Candidates" without uploading anything.
      const virtualFiles: UploadedFile[] = sample.sample_resumes.map((r) => {
        const safeName = r.name.replace(/\s+/g, "_").toLowerCase() + ".txt";
        const file = new File([r.content], safeName, { type: "text/plain" });
        return { file, name: safeName, size: file.size };
      });
      setFiles(virtualFiles);
    } catch {
      // Fall back to the offline JD if the API is unreachable.
      setJd(SAMPLE_JD);
    } finally {
      setSampleLoading(false);
    }
  };

  const filtered = useMemo(() => {
    const list = response?.candidates ?? [];
    return list
      .filter((c) => {
        if (filter === "all") return true;
        if (filter === "green") return c.score >= 80;
        if (filter === "yellow") return c.score >= 60 && c.score < 80;
        return c.score < 60;
      })
      .sort((a, b) => (sortDesc ? b.score - a.score : a.score - b.score));
  }, [response, filter, sortDesc]);

  const onDownloadCsv = () => {
    if (!response) return;
    const csv = candidatesToCsv(filtered.length ? filtered : response.candidates);
    const filename = `insync-scores-${response.job_summary.title.replace(/\s+/g, "-").toLowerCase()}.csv`;
    downloadCsv(filename, csv);
  };

  const jobTitle: JobSummary["title"] | "Job description" =
    response?.job_summary.title ?? "Job description";

  return (
    <div className="relative min-h-screen overflow-hidden noise-overlay">
      <CursorGlow />

      {/* Ambient hero glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-[100px] -z-10 h-[700px] w-[1000px] -translate-x-1/2 rounded-full opacity-30 blur-3xl"
        style={{ background: "radial-gradient(circle, var(--emerald-forest) 0%, transparent 65%)" }}
      />

      <Header />

      <main className="relative mx-auto max-w-6xl px-5 pb-24">
        <Hero />

        <div className="grid gap-5 md:grid-cols-2">
          <JDCard jd={jd} setJd={setJd} onLoadSample={onLoadSample} sampleLoading={sampleLoading} />
          <ResumesCard files={files} setFiles={setFiles} />
        </div>

        <div className="mt-8 flex flex-col items-center">
          <AnimatePresence mode="wait">
            {stage !== "loading" ? (
              <motion.div
                key="btn"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="w-full md:w-auto"
              >
                <button
                  onClick={onScore}
                  disabled={!canSubmit}
                  title={!canSubmit ? "Add a JD (50+ chars) and at least 1 resume" : undefined}
                  className={`group relative inline-flex w-full items-center justify-center gap-2 rounded-xl px-8 py-4 text-base font-bold transition-all md:w-[400px] ${
                    canSubmit
                      ? "bg-emerald text-primary-foreground glow-emerald animate-pulse-glow hover:bg-mint"
                      : "cursor-not-allowed bg-surface text-muted-foreground"
                  }`}
                >
                  Score Candidates
                  <ArrowRight
                    className={`h-4 w-4 transition-transform ${canSubmit ? "group-hover:translate-x-1.5" : ""}`}
                  />
                </button>
                {!canSubmit && (
                  <p className="mt-3 text-center text-xs text-muted-foreground">
                    Add a JD (50+ chars) and at least 1 resume to begin.
                  </p>
                )}
                {scoreError && (
                  <div className="mt-3 flex items-start gap-2 rounded-lg border border-danger/30 bg-danger/5 px-3 py-2 text-xs text-danger">
                    <AlertTriangle className="mt-[1px] h-3.5 w-3.5 shrink-0" /> {scoreError}
                  </div>
                )}
              </motion.div>
            ) : (
              <LoadingBlock key="load" progress={progress} />
            )}
          </AnimatePresence>
        </div>

        <AnimatePresence>
          {stage === "results" && response && (
            <motion.section
              ref={resultsRef}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5 }}
              className="mt-16"
            >
              <div className="mb-6 flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald">
                    Results
                  </div>
                  <h2 className="mt-2 text-2xl font-bold text-foreground">
                    {response.candidates.length} candidates scored against
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {jobTitle}
                    {response.job_summary.location ? ` — ${response.job_summary.location}` : ""}
                  </p>
                  {response.metadata.failed_resume_count > 0 && (
                    <p className="mt-1 text-xs text-warn">
                      {response.metadata.failed_resume_count} resume(s) couldn't be parsed and were
                      skipped.
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <button
                    onClick={() => setSortDesc((s) => !s)}
                    className="rounded-lg border border-hairline bg-surface/60 px-3 py-2 text-xs text-foreground/80 hover:border-emerald/30"
                  >
                    Sort: Score {sortDesc ? "↓" : "↑"}
                  </button>
                  <select
                    value={filter}
                    onChange={(e) => setFilter(e.target.value as typeof filter)}
                    className="rounded-lg border border-hairline bg-surface/60 px-3 py-2 text-xs text-foreground/80 hover:border-emerald/30 focus:border-emerald/40 focus:outline-none"
                  >
                    <option value="all">Filter: All</option>
                    <option value="green">Green (80+)</option>
                    <option value="yellow">Yellow (60–79)</option>
                    <option value="red">Red (&lt;60)</option>
                  </select>
                  <button
                    onClick={onDownloadCsv}
                    className="rounded-lg border border-hairline bg-surface/60 px-3 py-2 text-xs text-foreground/80 hover:border-emerald/30"
                  >
                    Export CSV
                  </button>
                </div>
              </div>

              <div className="space-y-3">
                {filtered.map((c, i) => (
                  <CandidateCard
                    key={c.candidate_id}
                    c={c}
                    defaultOpen={i < 3 && filter === "all"}
                    index={i}
                  />
                ))}
              </div>

              <HookCards
                response={response}
                sessionId={sessionId}
                prospectId={prospectId}
                onDownloadCsv={onDownloadCsv}
              />
            </motion.section>
          )}
        </AnimatePresence>
      </main>

      <footer className="relative border-t border-hairline">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-4 px-5 py-8 md:flex-row md:items-center">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <div className="h-4 w-4 rounded-sm bg-emerald/70" />
            Built by Insync — The Connection Layer for Logistics Recruitment
          </div>
          <div className="flex gap-5 text-xs text-muted-foreground">
            <a href="#" className="hover:text-foreground">
              Privacy
            </a>
            <a href="#" className="hover:text-foreground">
              Terms
            </a>
            <a href="#" className="hover:text-foreground">
              Contact
            </a>
          </div>
        </div>
        <div className="mx-auto max-w-6xl px-5 pb-6 font-mono text-[10px] text-muted-foreground/60">
          {"// session: " +
            sessionId.slice(0, 8) +
            (prospectId ? " · prospect: " + prospectId : "") +
            " · agent: insync.screener.v1"}
        </div>
      </footer>
    </div>
  );
}
