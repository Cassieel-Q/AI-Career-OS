import { MissionPage } from "../../../mission-page.tsx";

export default async function Page({ params }: { params: Promise<{ missionId: string }> }) {
  const { missionId } = await params;
  return <MissionPage missionId={missionId} currentTab="resume" />;
}
