import { RoleExplorationStep } from "../../../role-exploration-step";
import { WorkflowRoute } from "../../../workflow-route";

export default async function RoleExplorationWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return (
    <WorkflowRoute
      profileId={profileId}
      currentStep="role-exploration"
      renderStep={(snapshot, controls) => <RoleExplorationStep snapshot={snapshot} controls={controls} />}
    />
  );
}
