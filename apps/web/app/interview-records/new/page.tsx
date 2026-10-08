import { InterviewRecordsNew } from "../../interview-records-new.tsx";

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ company?: string }>;
}) {
  const sp = await searchParams;
  return <InterviewRecordsNew initialCompany={sp.company?.trim() || ""} />;
}
