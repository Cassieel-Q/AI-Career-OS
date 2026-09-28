"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { canEnterProofStep, proofHref, PROOF_STEPS, PROOF_STEP_LABELS } from "./proof-state.ts";
import type { ProofSnapshot, ProofStep } from "./proof-state.ts";

type ProofShellProps = {
  profileId: string;
  missionId?: string;
  currentStep: ProofStep;
  snapshot: ProofSnapshot | null;
  children: ReactNode;
  loading?: boolean;
  busy?: boolean;
  nextReady?: boolean;
  error?: string;
  onNext?: () => void;
  onRetry?: () => void;
};

export function ProofShell({ profileId, missionId, currentStep, snapshot, children, loading = false, busy = false, nextReady = false, error = "", onNext, onRetry }: ProofShellProps) {
  const router = useRouter();
  const missionInterview = Boolean(missionId);
  const index = PROOF_STEPS.indexOf(currentStep);
  const previous = index > 0 ? proofHref(profileId, PROOF_STEPS[index - 1], missionId) : null;
  const next = index >= 0 && index < PROOF_STEPS.length - 1 ? proofHref(profileId, PROOF_STEPS[index + 1], missionId) : null;
  const nextDisabled = loading || busy || !nextReady || !next;
  const nextLabel = currentStep === "interview"
    ? (snapshot?.session?.status === "COMPLETED" ? "查看面试复盘" : "提交回答并生成下一题")
    : `继续：${PROOF_STEP_LABELS[PROOF_STEPS[index + 1]]}`;

  return (
    <main className="workflow-shell">
      <header className="workflow-header">
        <Link className="workflow-brand" href="/missions" aria-label="AI Career OS — 我的岗位准备">
          <span className="workflow-brand-mark" aria-hidden="true">A</span>
          <span>AI Career OS</span>
        </Link>
        <div className="workflow-profile-context"><span>{missionInterview ? "模拟面试" : "证明工作区"}</span>{missionInterview ? null : <code>{profileId}</code>}</div>
      </header>
      <div className={missionInterview ? "workflow-layout mission-interview-layout" : "workflow-layout"}>
        <aside className="workflow-sidebar" style={missionInterview ? { display: "none" } : undefined}>
          <p className="workflow-sidebar-title">{missionInterview ? "模拟面试" : "简历 → 证明"}</p>
          <nav aria-label="证明进度">
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
          <button type="button" className="button-secondary workflow-previous" disabled={loading || busy || (!previous && !missionInterview)} onClick={() => missionInterview ? router.push(`/missions/${missionId}/interview`) : previous && router.push(previous)}><span aria-hidden="true">←</span> {missionInterview ? "返回面试准备" : "上一步"}</button>
            {next ? <button type="button" className="workflow-next" disabled={nextDisabled} onClick={onNext}>{busy ? (currentStep === "interview" ? "正在评分…" : "正在保存…") : nextLabel}<span aria-hidden="true">→</span></button> : <p className="workflow-terminal" role="status">{currentStep === "re-evaluate" ? "请选择一个补强方向" : "当前证明链已完成"}</p>}
          </footer>
        </section>
      </div>
    </main>
  );
}
