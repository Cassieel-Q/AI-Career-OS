import { WorkflowPage } from "../../../workflow-page";

export default async function PreferencesWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return <WorkflowPage profileId={profileId} currentStep="preferences" />;
}
