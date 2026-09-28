import { redirect } from "next/navigation";
import { ProofPageClient } from "../../../proof-page-client.tsx";

export default async function ProofPage({ params, searchParams }: { params: Promise<{ profileId: string }>; searchParams: Promise<{ mission_id?: string }> }) {
  const { profileId } = await params;
  const { mission_id: missionId } = await searchParams;
  if (missionId) redirect(`/missions/${encodeURIComponent(missionId)}/interview`);
  return <ProofPageClient profileId={profileId} missionId={missionId} currentStep="claim-check" />;
}
