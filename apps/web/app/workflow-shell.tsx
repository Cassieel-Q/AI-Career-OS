"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";

import {
  canEnterStep,
  workflowHref,
} from "./workflow-state.ts";
import type { WorkflowSnapshot, WorkflowStep } from "./workflow-state.ts";
import {
  stepIndicatorState,
  stepNavigation,
  stepNumber,
} from "./workflow-navigation.ts";

type WorkflowShellProps = {
  profileId: string;
  currentStep: WorkflowStep;
  snapshot: WorkflowSnapshot | null;
  children: ReactNode;
  loading?: boolean;
  busy?: boolean;
  nextReady?: boolean;
  error?: string;
  onNext?: () => void;
  onRetry?: () => void;
};

export function WorkflowShell({
  profileId,
  currentStep,
  snapshot,
  children,
  loading = false,
  busy = false,
  nextReady = false,
  error = "",
  onNext,
  onRetry,
}: WorkflowShellProps) {
  const router = useRouter();
  const nav = stepNavigation(profileId, currentStep);
  const indicators = snapshot ? stepIndicatorState(snapshot, currentStep) : [];
  const nextDisabled = loading || busy || !nextReady || !nav.next;

  return (
    <main className="workflow-shell">
      <header className="workflow-header">
        <Link className="workflow-brand" href="/workflow/start" aria-label="AI Career OS — workflow start">
          <span className="workflow-brand-mark" aria-hidden="true">A</span>
          <span>AI Career OS</span>
        </Link>
        <div className="workflow-profile-context">
          <span>当前 Profile</span>
          <code>{profileId}</code>
        </div>
      </header>

      <div className="workflow-layout">
        <aside className="workflow-sidebar">
          <p className="workflow-sidebar-title">职业规划流程</p>
          <nav aria-label="Workflow progress">
            <ol className="workflow-step-list">
              {indicators.map((item, index) => {
                const canVisit = Boolean(snapshot && canEnterStep(snapshot, item.step));
                const marker = item.complete ? "✓" : item.current ? "●" : String(index + 1);
                return (
                  <li key={item.step} className={item.current ? "workflow-step current" : item.complete ? "workflow-step complete" : "workflow-step"}>
                    <button
                      type="button"
                      className="workflow-step-button"
                      aria-current={item.current ? "step" : undefined}
                      disabled={!canVisit || loading || busy}
                      onClick={() => router.push(workflowHref(profileId, item.step))}
                    >
                      <span className="workflow-step-marker" aria-hidden="true">{marker}</span>
                      <span className="workflow-step-label">{item.label}</span>
                      <span className="sr-only">
                        {item.complete ? "已完成" : item.current ? "当前步骤" : "尚未完成"}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </nav>
        </aside>

        <section className="workflow-main" aria-label={`Step ${stepNumber(currentStep)}: ${indicators.find((item) => item.current)?.label ?? currentStep}`}>
          <div className="workflow-mobile-indicator" aria-live="polite">
            <span>Step {stepNumber(currentStep)} of 5</span>
            <strong id="workflow-current-title">{indicators.find((item) => item.current)?.label ?? currentStep}</strong>
          </div>
          <div className="workflow-content-panel">
            {loading ? (
              <div className="workflow-loading" role="status" aria-live="polite">
                <span className="loading-indicator" aria-hidden="true" />
                <p>正在从服务器恢复当前步骤…</p>
              </div>
            ) : error ? (
              <div className="workflow-error-state">
                <p className="message error" role="alert">{error}</p>
                {onRetry && <button type="button" className="button-secondary" onClick={onRetry}>重试</button>}
              </div>
            ) : (
              children
            )}
          </div>

          <footer className="workflow-navigation">
            <button
              type="button"
              className="button-secondary workflow-previous"
              disabled={!nav.previous || loading || busy}
              onClick={() => nav.previous && router.push(nav.previous)}
            >
              <span aria-hidden="true">←</span> 上一步
            </button>
            {nav.next ? (
              <button type="button" className="workflow-next" disabled={nextDisabled} onClick={onNext}>
                {busy ? "正在保存…" : nav.nextLabel}
                <span aria-hidden="true">→</span>
              </button>
            ) : (
              <p className="workflow-terminal" role="status">已达到当前阶段</p>
            )}
          </footer>
        </section>
      </div>
    </main>
  );
}
