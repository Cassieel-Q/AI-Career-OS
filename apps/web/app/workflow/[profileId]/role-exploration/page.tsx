import { WorkflowPage } from "../../../workflow-page";

export default async function RoleExplorationWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return <WorkflowPage profileId={profileId} currentStep="role-exploration" />;
}
