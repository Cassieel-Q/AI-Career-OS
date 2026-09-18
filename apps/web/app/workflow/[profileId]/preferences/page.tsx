import { PreferencesStep } from "../../../preferences-step";
import { WorkflowRoute } from "../../../workflow-route";

export default async function PreferencesWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return (
    <WorkflowRoute
      profileId={profileId}
      currentStep="preferences"
      renderStep={(snapshot, controls) => snapshot.profile && <PreferencesStep profile={snapshot.profile} controls={controls} />}
    />
  );
}
