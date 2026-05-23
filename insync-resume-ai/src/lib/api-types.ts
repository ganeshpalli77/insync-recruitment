// Wire types mirror the Pydantic schemas in insync-backend/src/schemas/*.py.
// Keep snake_case to match the API exactly — no client-side renaming.

export type ScoreBand = "strong" | "moderate" | "weak";
export type CommuteRisk = "low" | "medium" | "high" | "unknown";
export type Metro = "atlanta" | "dfw" | "columbus" | "other";

export type JobSummary = {
  title: string;
  location: string;
  company: string | null;
  required_experience_years: number | null;
  required_certifications: string[];
  key_skills: string[];
};

export type LocationMatch = {
  candidate_location: string | null;
  distance_estimate_miles: number | null;
  commute_risk: CommuteRisk;
};

export type ExperienceMatch = {
  years_relevant: number;
  matches_requirement: boolean;
  notes: string;
};

export type CandidateScore = {
  candidate_id: string;
  name: string;
  score: number; // 0–100
  score_band: ScoreBand;
  one_line_summary: string;
  strengths: string[];
  gaps: string[];
  interview_questions: string[];
  location_match: LocationMatch | null;
  experience_match: ExperienceMatch;
  raw_resume_text: string;
};

export type ScoringMetadata = {
  processing_time_ms: number;
  model_parser: string;
  model_scorer: string;
  total_tokens_used: number;
  total_cost_usd: number;
  cache_hit: boolean;
  failed_resume_count: number;
};

export type ScoreResponse = {
  job_summary: JobSummary;
  candidates: CandidateScore[];
  metadata: ScoringMetadata;
  session_id: string;
  // True when the prospect already submitted the email gate on a prior
  // visit. False ⇒ frontend should show the gate before revealing results.
  lead_registered: boolean;
};

export type LeadRegisterRequest = {
  prospect_id: string;
  name: string;
  email: string;
  company_name: string;
  session_id: string;
};

export type LeadRegisterResponse = {
  success: boolean;
  total_resumes_scored: number;
};

export type ScoreProgressEvent = {
  completed: number;
  total: number;
  candidate_name: string | null;
};

export type SampleResume = {
  name: string;
  content: string;
  expected_score_band: string;
};

export type SampleDataResponse = {
  job_description: string;
  sample_resumes: SampleResume[];
};

export type EmailCaptureResponse = {
  success: boolean;
  message: string;
};

export type LeadsRequestResponse = {
  success: boolean;
  next_steps_message: string;
};
