import { INTERVIEW_ROUNDS, type InterviewRound } from "../../interview-records.ts";
import { InterviewRecordsNew } from "../../interview-records-new.tsx";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ company?: string; round?: string }>;
}) {
  const sp = await searchParams;
  const requested = sp.round?.trim() ?? "";
  const round: InterviewRound = (INTERVIEW_ROUNDS as readonly string[]).includes(requested)
    ? (requested as InterviewRound)
    : "一面";
  return <InterviewRecordsNew initialCompany={sp.company?.trim() || ""} initialRound={round} />;
}
