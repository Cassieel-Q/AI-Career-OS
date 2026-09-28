import { ProofPageClient } from "../../../proof-page-client.tsx";

export default async function ProofPage({ params, searchParams }: { params: Promise<{ profileId: string }>; searchParams: Promise<{ mission_id?: string }> }) {
  const { profileId } = await params;
  const { mission_id: missionId } = await searchParams;
  return <ProofPageClient profileId={profileId} missionId={missionId} currentStep="target-job" />;
}
