"use client";

import { useEffect, useRef, useState } from "react";

import {
  ROLE_EXPLORATION_DISCLAIMER,
  ROLE_EXPLORATION_LEVEL_LABELS,
  ROLE_EXPLORATION_GENERATION_ERROR,
  createRoleExplorationRequest,
  roleExplorationGenerationView,
  roleExplorationViewData,
} from "./role-exploration.ts";
import type { RoleExplorationRead } from "./role-exploration.ts";
import type { WorkflowStepControls } from "./workflow-route.tsx";
import type { WorkflowSnapshot } from "./workflow-state.ts";

export function RoleExplorationStep({ snapshot, controls }: { snapshot: WorkflowSnapshot; controls: WorkflowStepControls }) {
  const [exploration, setExploration] = useState<RoleExplorationRead | null>(snapshot.roleExploration);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const profile = snapshot.profile;
  const setNextReady = controls.setNextReady;

  useEffect(() => setExploration(snapshot.roleExploration), [snapshot.roleExploration]);
  useEffect(() => {
    setNextReady(Boolean(exploration && exploration.profile_id === profile?.profile_id));
  }, [exploration, profile?.profile_id, setNextReady]);

  async function generate() {
    if (!profile || inFlight.current || controls.busy) return;
    inFlight.current = true;
    setCreating(true);
    setError("");
    try {
      const created = await createRoleExplorationRequest(profile.profile_id, controls.apiUrl);
      setExploration(created);
      await controls.refresh();
    } catch {
      setError(ROLE_EXPLORATION_GENERATION_ERROR);
    } finally {
      inFlight.current = false;
      setCreating(false);
    }
  }

  const disabled = creating || controls.busy;
  const generationView = roleExplorationGenerationView(creating, error);

  return (
    <div className="workflow-step-content">
      <div className="step-heading">
        <p className="section-kicker">Step 3 · Role Exploration</p>
        <h1 id="workflow-step-title">探索适合你的岗位方向</h1>
        <p className="summary">系统会结合已确认的 Profile、已保存的职业偏好和内置岗位画像，提供可追溯的探索理由。</p>
      </div>
      {!exploration ? (
        <section className="step-empty-state" aria-label="Role exploration empty state">
          <div className="empty-state-icon" aria-hidden="true">↗</div>
          <h2>准备好开始岗位探索</h2>
          <p>此结果只提供探索性建议，不代表真实市场录用概率或岗位匹配百分比。</p>
          {error && <p className="message error" role="alert">{error}</p>}
          <button type="button" onClick={() => void generate()} disabled={disabled}>
            {generationView.buttonLabel}
          </button>
          {creating && <p className="profile-note" role="status" aria-live="polite">正在根据你的 Profile 和职业偏好探索岗位…</p>}
        </section>
      ) : (
        <section className="role-exploration" aria-label="Role exploration results">
          <div className="section-heading">
            <div>
              <p className="section-kicker">系统探索结果</p>
              <h2>六个岗位方向</h2>
            </div>
            <span className="role-version">{exploration.role_profile_version}</span>
          </div>
          <div className="role-card-grid">
            {roleExplorationViewData(exploration).map((item) => (
              <article className="role-card" key={item.role_code}>
                <div className="role-card-heading">
                  <h3>{item.role_name}</h3>
                  <span className={`role-level ${item.level.toLowerCase()}`}>{ROLE_EXPLORATION_LEVEL_LABELS[item.level]}</span>
                </div>
                <div className="role-card-list">
                  <strong>核心解释</strong>
                  <ul>{item.reasons.map((reason, index) => <li key={`${item.role_code}-reason-${index}`}>{reason}</li>)}</ul>
                </div>
                {item.concerns.length > 0 && (
                  <div className="role-card-list concern">
                    <strong>需要留意</strong>
                    <ul>{item.concerns.map((concern, index) => <li key={`${item.role_code}-concern-${index}`}>{concern}</li>)}</ul>
                  </div>
                )}
                <p className="role-refs"><span>Profile evidence</span>{item.evidence_refs.join(", ") || "—"}</p>
                <p className="role-refs"><span>Preference refs</span>{item.preference_refs.join(", ") || "—"}</p>
              </article>
            ))}
          </div>
          <p className="role-disclaimer">{ROLE_EXPLORATION_DISCLAIMER}</p>
          {error && <p className="message error" role="alert">{error}</p>}
          <button type="button" className="button-secondary" onClick={() => void generate()} disabled={disabled}>
            {creating ? "正在生成…" : "重新探索岗位"}
          </button>
          {creating && <p className="profile-note" role="status" aria-live="polite">正在根据你的 Profile 和职业偏好探索岗位…</p>}
        </section>
      )}
    </div>
  );
}
