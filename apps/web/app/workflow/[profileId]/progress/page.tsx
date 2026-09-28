import { WorkflowPage } from "../../../workflow-page.tsx";

export default async function ProgressPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return <WorkflowPage profileId={profileId} currentStep="progress" />;
}
