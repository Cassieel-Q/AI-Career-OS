import { StudioPage } from "../../../../resume-studio/studio-page.tsx";

export default async function Page({ params }: { params: Promise<{ missionId: string }> }) {
  const { missionId } = await params;
  return <StudioPage missionId={missionId} />;
}
