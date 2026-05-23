import { createFileRoute } from "@tanstack/react-router";
import ResumeScreener from "@/components/ResumeScreener";

type IndexSearch = {
  p?: string; // prospect_id, used for Track B attribution
};

export const Route = createFileRoute("/")({
  validateSearch: (search: Record<string, unknown>): IndexSearch => ({
    p: typeof search.p === "string" && search.p.length > 0 ? search.p : undefined,
  }),
  component: IndexComponent,
  head: () => ({
    meta: [
      { title: "AI Resume Screener for Logistics Recruiters | Insync" },
      {
        name: "description",
        content:
          "Free AI resume screener for logistics recruitment agencies. Drop a JD, upload resumes, get ranked candidates in 30 seconds. No signup.",
      },
      { property: "og:title", content: "AI Resume Screener for Logistics Recruiters | Insync" },
      {
        property: "og:description",
        content: "Score and rank logistics candidates against any job description in 30 seconds.",
      },
    ],
  }),
});

function IndexComponent() {
  const { p } = Route.useSearch();
  return <ResumeScreener prospectId={p ?? null} />;
}
