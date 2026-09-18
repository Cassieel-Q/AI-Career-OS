import { TargetRoleStep } from "../../../target-role-step";
import { WorkflowRoute } from "../../../workflow-route";

export default async function TargetRoleWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return (
    <WorkflowRoute
      profileId={profileId}
      currentStep="target-role"
      renderStep={(snapshot, controls) => <TargetRoleStep snapshot={snapshot} controls={controls} />}
    />
  );
}
