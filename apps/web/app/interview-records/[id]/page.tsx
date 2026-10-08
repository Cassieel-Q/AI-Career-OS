import { InterviewRecordsDetail } from "../../interview-records-detail.tsx";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <InterviewRecordsDetail recordId={id} />;
}
