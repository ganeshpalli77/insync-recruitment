// Persistent prospect_id for the email-gate dedup.
//
// Precedence: URL ?p= wins (campaign tracking); else localStorage; else
// mint a fresh UUID. Whatever we end up with is written back to
// localStorage so the next visit (today, tomorrow, next week) reuses it
// and the backend recognizes the returning lead — no re-prompt for email.

const KEY = "insync_prospect_id";

export function getOrCreateProspectId(urlProspectId: string | null): string {
  if (urlProspectId) {
    try {
      localStorage.setItem(KEY, urlProspectId);
    } catch {
      // localStorage unavailable (SSR, incognito with strict mode) — fine.
    }
    return urlProspectId;
  }
  try {
    const existing = localStorage.getItem(KEY);
    if (existing) return existing;
    const fresh =
      typeof crypto !== "undefined" && "randomUUID" in crypto
        ? crypto.randomUUID()
        : `p-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    // No persistence available — return an ephemeral id. The user will
    // hit the email gate every visit until they enable localStorage,
    // which is acceptable degradation.
    return typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `p-eph-${Date.now()}`;
  }
}
