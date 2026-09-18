"use client";

import { JobDescriptionsSection } from "./job-descriptions-section.tsx";
import { PreferencesStep } from "./preferences-step.tsx";
import { ProfileStep } from "./profile-step.tsx";
import { RoleExplorationStep } from "./role-exploration-step.tsx";
import { TargetRoleStep } from "./target-role-step.tsx";
import { WorkflowRoute } from "./workflow-route.tsx";
import type { WorkflowSnapshot, WorkflowStep } from "./workflow-state.ts";
import type { WorkflowStepControls } from "./workflow-route.tsx";

type DynamicWorkflowStep = Exclude<WorkflowStep, "start">;

export function WorkflowPage({ profileId, currentStep }: { profileId: string; currentStep: DynamicWorkflowStep }) {
  return (
    <WorkflowRoute
      profileId={profileId}
      currentStep={currentStep}
      renderStep={(snapshot, controls) => renderWorkflowStep(currentStep, snapshot, controls)}
    />
  );
}

function renderWorkflowStep(step: DynamicWorkflowStep, snapshot: WorkflowSnapshot, controls: WorkflowStepControls) {
  if (step === "profile") {
    return snapshot.profile ? <ProfileStep profile={snapshot.profile} controls={controls} /> : null;
  }
  if (step === "preferences") {
    return snapshot.profile ? <PreferencesStep profile={snapshot.profile} controls={controls} /> : null;
  }
  if (step === "role-exploration") {
    return <RoleExplorationStep snapshot={snapshot} controls={controls} />;
  }
  if (step === "target-role") {
    return <TargetRoleStep snapshot={snapshot} controls={controls} />;
  }
  return snapshot.targetRole ? (
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
        initialRecords={snapshot.jobDescriptions.filter((record) => record.target_role_id === snapshot.targetRole?.id)}
      />
    </div>
  ) : null;
}
