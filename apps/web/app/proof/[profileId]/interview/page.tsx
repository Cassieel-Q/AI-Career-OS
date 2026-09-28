import { ProofPageClient } from "../../../proof-page-client.tsx";

export default async function ProofPage({
  params,
  searchParams,
}: {
  params: Promise<{ profileId: string }>;
  searchParams: Promise<{ mission_id?: string; fresh?: string }>;
}) {
  const { profileId } = await params;
  const sp = await searchParams;
  const missionId = sp.mission_id;
  const freshStart = sp.fresh === "1";
  return (
    <ProofPageClient
      profileId={profileId}
      missionId={missionId}
      currentStep="interview"
      freshStart={freshStart}
    />
  );
}
