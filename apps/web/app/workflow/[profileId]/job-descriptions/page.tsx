import { JobDescriptionsSection } from "../../../job-descriptions-section";
import { WorkflowRoute } from "../../../workflow-route";

export default async function JobDescriptionsWorkflowPage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return (
    <WorkflowRoute
      profileId={profileId}
      currentStep="job-descriptions"
      renderStep={(snapshot, controls) => snapshot.targetRole ? (
        <div className="workflow-step-content">
          <div className="step-heading">
            <p className="section-kicker">Step 5 · Job Descriptions</p>
            <h1 id="workflow-step-title">为当前目标岗位建立真实市场样本</h1>
            <p className="summary">粘贴真实招聘描述。每个样本保留原文，并绑定到你当前选择的目标岗位。</p>
          </div>
          <JobDescriptionsSection
            key={snapshot.targetRole.id}
            targetRole={snapshot.targetRole}
            apiUrl={controls.apiUrl}
            initialRecords={snapshot.jobDescriptions}
          />
        </div>
      ) : null}
    />
  );
}
