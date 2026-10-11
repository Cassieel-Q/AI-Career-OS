"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";

import { canEnterProofStep, proofHref, PROOF_STEPS, PROOF_STEP_LABELS } from "./proof-state.ts";
import type { ProofSnapshot, ProofStep } from "./proof-state.ts";
import { readMission, readTargetResumes } from "./missions.ts";
import type { Mission } from "./missions.ts";
import { deriveMissionProgress } from "./mission-progress.ts";
import { MissionProgress } from "./mission-progress.tsx";

type ProofShellProps = {
  profileId: string;
  missionId?: string;
  currentStep: ProofStep;
  snapshot: ProofSnapshot | null;
  children: ReactNode;
  loading?: boolean;
  busy?: boolean;
  nextReady?: boolean;
  nextLabelOverride?: string | null;
  error?: string;
  onNext?: () => void;
  onRetry?: () => void;
};

export function ProofShell({ profileId, missionId, currentStep, snapshot, children, loading = false, busy = false, nextReady = false, nextLabelOverride = null, error = "", onNext, onRetry }: ProofShellProps) {
  const router = useRouter();
  const [mission, setMission] = useState<Mission | null>(null);
  const [confirmedResume, setConfirmedResume] = useState(false);
  useEffect(() => {
    if (!missionId) return;
    let cancelled = false;
    void Promise.all([readMission(missionId), readTargetResumes(missionId)]).then(([loaded, resumes]) => {
      if (cancelled) return;
      setMission(loaded);
      setConfirmedResume(resumes.some((item) => item.status === "CONFIRMED"));
    }).catch(() => { /* The active interview stays usable if progress metadata is temporarily unavailable. */ });
    return () => { cancelled = true; };
  }, [missionId]);
  const missionInterview = Boolean(missionId);
  const index = PROOF_STEPS.indexOf(currentStep);
  const previous = index > 0 ? proofHref(profileId, PROOF_STEPS[index - 1], missionId) : null;
  const next = missionInterview && currentStep === "debrief" ? null : index >= 0 && index < PROOF_STEPS.length - 1 ? proofHref(profileId, PROOF_STEPS[index + 1], missionId) : null;
  const nextDisabled = loading || busy || !nextReady || !next;
  const nextLabel = nextLabelOverride ?? (currentStep === "interview"
    ? (snapshot?.session?.status === "COMPLETED" ? "查看面试复盘" : "提交回答并生成下一题")
    : `继续：${PROOF_STEP_LABELS[PROOF_STEPS[index + 1]]}`);

  return (
    <main className="workflow-shell">
      {missionId && mission && <MissionProgress steps={deriveMissionProgress({
        missionId,
        workflowState: mission.workflow_state,
        currentTab: currentStep === "interview" ? "interview" : currentStep === "debrief" || currentStep === "proof-actions" || currentStep === "re-evaluate" ? "outcome" : "resume",
        resumeBound: Boolean(mission.resume_source?.mode),
        targetConfirmed: confirmedResume,
        sessionStatus: snapshot?.session?.status ?? null,
      })} />}
      <div className={missionInterview ? "workflow-layout mission-interview-layout" : "workflow-layout"}>
        <aside className="workflow-sidebar" style={missionInterview ? { display: "none" } : undefined}>
          <p className="workflow-sidebar-title">{missionInterview ? "模拟面试" : "简历 → 面试准备"}</p>
          <nav aria-label="面试准备进度">
            <ol className="workflow-step-list">
              {PROOF_STEPS.map((step, stepIndex) => {
                const current = step === currentStep;
                const complete = stepIndex < index && Boolean(snapshot && canEnterProofStep(snapshot, step));
                const canVisit = Boolean(snapshot && canEnterProofStep(snapshot, step));
                return (
                  <li key={step} className={current ? "workflow-step current" : complete ? "workflow-step complete" : "workflow-step"}>
                    <button type="button" className="workflow-step-button" aria-current={current ? "step" : undefined} disabled={!canVisit || loading || busy} onClick={() => router.push(proofHref(profileId, step, missionId))}>
                      <span className="workflow-step-marker" aria-hidden="true">{complete ? "✓" : current ? "●" : String(stepIndex + 1)}</span>
                      <span className="workflow-step-label">{PROOF_STEP_LABELS[step]}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        </aside>
        <section className="workflow-main" aria-label={`${PROOF_STEP_LABELS[currentStep]} step`}>
          <div className="workflow-mobile-indicator" aria-live="polite">
            {missionInterview ? <><span>模拟面试</span><strong>回答问题</strong></> : <><span>第 {index + 1} / {PROOF_STEPS.length} 步</span><strong>{PROOF_STEP_LABELS[currentStep]}</strong></>}
          </div>
          <div className="workflow-content-panel">
            {loading ? <div className="workflow-loading" role="status" aria-live="polite"><span className="loading-indicator" aria-hidden="true" /><p>正在加载当前面试内容…</p></div> : error && !(missionInterview && snapshot) ? <div className="workflow-error-state"><p className="message error" role="alert">{error}</p>{onRetry && <button type="button" className="button-secondary" onClick={onRetry}>重试</button>}</div> : <>{error ? <p className="message error" role="alert">{error}</p> : null}{children}</>}
          </div>
          <footer className="workflow-navigation">
          <button type="button" className="button-secondary workflow-previous" disabled={loading || busy || (!previous && !missionInterview)} onClick={() => missionInterview ? router.push(`/missions/${missionId}/interview`) : previous && router.push(previous)}><span aria-hidden="true">←</span> {missionInterview ? "返回岗位档案" : "上一步"}</button>
            {next ? <button type="button" className="workflow-next" disabled={nextDisabled} onClick={onNext}>{busy ? (currentStep === "interview" ? "正在评分…" : "正在保存…") : nextLabel}<span aria-hidden="true">→</span></button> : <p className="workflow-terminal" role="status">请选择需要的补强方式</p>}
          </footer>
        </section>
      </div>
    </main>
  );
}
