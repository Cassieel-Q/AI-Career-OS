"use client";

import { ProofRoute } from "./proof-route.tsx";
import { ProofStepView } from "./proof-steps.tsx";
import type { ProofStep } from "./proof-state.ts";

type Props = {
  profileId: string;
  missionId?: string;
  currentStep: ProofStep;
  freshStart?: boolean;
};

/** Client boundary so Server page.tsx never passes function props into ProofRoute. */
export function ProofPageClient({ profileId, missionId, currentStep, freshStart = false }: Props) {
  return (
    <ProofRoute
      profileId={profileId}
      missionId={missionId}
      currentStep={currentStep}
      renderStep={(snapshot, controls) => (
        <ProofStepView step={currentStep} snapshot={snapshot} controls={controls} freshStart={freshStart} />
      )}
    />
  );
}
