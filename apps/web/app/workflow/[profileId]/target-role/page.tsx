import { redirect } from "next/navigation";

export default async function TargetRoleWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  redirect(`/workflow/${encodeURIComponent(profileId)}/role-exploration`);
}
