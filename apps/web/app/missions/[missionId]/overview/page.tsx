import { redirect } from "next/navigation";

/** Compatibility: /overview → /role (岗位理解). */
export default async function OverviewRedirect({ params }: { params: Promise<{ missionId: string }> }) {
  const { missionId } = await params;
  redirect(`/missions/${encodeURIComponent(missionId)}/role`);
}
