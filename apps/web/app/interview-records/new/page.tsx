import { INTERVIEW_ROUNDS, type InterviewRound } from "../../interview-records.ts";
import { InterviewRecordsNew } from "../../interview-records-new.tsx";
import { readSearchParam, type SearchParamValue } from "../../search-params.ts";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ company?: SearchParamValue; round?: SearchParamValue }>;
}) {
  const sp = await searchParams;
  const requested = readSearchParam(sp.round);
  const round: InterviewRound = (INTERVIEW_ROUNDS as readonly string[]).includes(requested)
    ? (requested as InterviewRound)
    : "一面";
  return <InterviewRecordsNew initialCompany={readSearchParam(sp.company)} initialRound={round} />;
}
