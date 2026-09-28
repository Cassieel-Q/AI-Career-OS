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
import type { RoleCode, RoleExplorationRead } from "./role-exploration.ts";
import type { TargetRoleRead } from "./target-role.ts";
import { selectTargetRoleRequest, targetRoleMatchesExploration, targetRoleViewData } from "./target-role.ts";
import type { WorkflowStepControls } from "./workflow-route.tsx";
import type { WorkflowSnapshot } from "./workflow-state.ts";

export function RoleExplorationStep({ snapshot, controls }: { snapshot: WorkflowSnapshot; controls: WorkflowStepControls }) {
  const [exploration, setExploration] = useState<RoleExplorationRead | null>(snapshot.roleExploration);
  const [targetRole, setTargetRole] = useState<TargetRoleRead | null>(snapshot.targetRole);
  const [creating, setCreating] = useState(false);
  const [selecting, setSelecting] = useState<RoleCode | null>(null);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const profile = snapshot.profile;
  const setNextReady = controls.setNextReady;

  useEffect(() => {
    setExploration(snapshot.roleExploration);
    setTargetRole(snapshot.targetRole);
  }, [snapshot.roleExploration, snapshot.targetRole]);

  const currentTarget = targetRoleViewData(
    targetRoleMatchesExploration(targetRole, exploration) ? targetRole : null,
  );
  const hasCurrentTarget = Boolean(currentTarget);

  useEffect(() => {
    setNextReady(
      !creating &&
        selecting === null &&
        !controls.busy &&
        Boolean(exploration && exploration.profile_id === profile?.profile_id && hasCurrentTarget),
    );
  }, [controls.busy, creating, exploration, hasCurrentTarget, profile?.profile_id, selecting, setNextReady]);

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

  async function chooseTargetRole(roleCode: RoleCode) {
    if (!profile || !exploration || inFlight.current || controls.busy) return;
    inFlight.current = true;
    setSelecting(roleCode);
    setError("");
    try {
      const selected = await selectTargetRoleRequest(profile.profile_id, roleCode, controls.apiUrl);
      setTargetRole(selected);
      await controls.refresh();
    } catch (selectionError) {
      setError(selectionError instanceof Error ? selectionError.message : "目标岗位保存失败，请重试。");
    } finally {
      inFlight.current = false;
      setSelecting(null);
    }
  }

  const disabled = creating || selecting !== null || controls.busy;
  const generationView = roleExplorationGenerationView(creating, error);

  return (
    <div className="workflow-step-content">
      <div className="step-heading">
        <p className="section-kicker">Step 3 · Role Selection</p>
        <h1 id="workflow-step-title">探索并选择目标岗位</h1>
        <p className="summary">AI 先根据已确认的 Profile 和职业偏好提供六个方向，再由你选择唯一的当前目标岗位。推荐等级只提供参考，任何方向都可以选择。</p>
      </div>

      {!exploration ? (
        <section className="step-empty-state" aria-label="Role selection empty state">
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
        <>
          <section className="role-exploration" aria-label="Role selection results">
            <div className="section-heading">
              <div>
                <p className="section-kicker">AI 推荐结果</p>
                <h2>六个岗位方向</h2>
              </div>
              <span className="role-version">{exploration.role_profile_version}</span>
            </div>
            <div className="role-card-grid">
              {roleExplorationViewData(exploration).map((item) => {
                const selected = currentTarget?.role_code === item.role_code;
                return (
                  <article className={selected ? "role-card selected-target" : "role-card"} key={item.role_code}>
                    <div className="role-card-heading">
                      <h3>{item.role_name}</h3>
                      <span className={`role-level ${item.level.toLowerCase()}`}>{ROLE_EXPLORATION_LEVEL_LABELS[item.level]}</span>
                    </div>
                    <p className="role-refs"><span>AI 推荐等级</span>{ROLE_EXPLORATION_LEVEL_LABELS[item.level]}</p>
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
                    <button type="button" className="target-role-button" disabled={disabled} onClick={() => void chooseTargetRole(item.role_code)}>
                      {selecting === item.role_code ? "保存中…" : selected ? "当前目标岗位" : "选择为目标岗位"}
                    </button>
                  </article>
                );
              })}
            </div>
            <p className="role-disclaimer">{ROLE_EXPLORATION_DISCLAIMER}</p>
            {error && <p className="message error" role="alert">{error}</p>}
            <button type="button" className="button-secondary" onClick={() => void generate()} disabled={disabled}>
              {generationView.buttonLabel}
            </button>
            {creating && <p className="profile-note" role="status" aria-live="polite">正在根据你的 Profile 和职业偏好探索岗位…</p>}
          </section>

          <section className="final-target-panel" aria-labelledby="final-target-title" aria-live="polite">
            <div>
              <p className="section-kicker">你的最终选择</p>
              <h2 id="final-target-title">{currentTarget?.role_name ?? "尚未选择目标岗位"}</h2>
            </div>
            {currentTarget && <span className="target-role-badge">由你选择</span>}
          </section>
        </>
      )}
    </div>
  );
}
