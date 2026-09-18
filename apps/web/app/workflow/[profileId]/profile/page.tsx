import { ProfileStep } from "../../../profile-step";
import { WorkflowRoute } from "../../../workflow-route";

export default async function ProfileWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return (
    <WorkflowRoute
      profileId={profileId}
      currentStep="profile"
      renderStep={(snapshot, controls) => snapshot.profile && <ProfileStep profile={snapshot.profile} controls={controls} />}
    />
  );
}
