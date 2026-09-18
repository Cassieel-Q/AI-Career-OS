"use client";

import { useEffect, useRef, useState } from "react";

import { ROLE_EXPLORATION_LEVEL_LABELS, roleExplorationViewData } from "./role-exploration.ts";
import type { RoleCode } from "./role-exploration.ts";
import type { TargetRoleRead } from "./target-role.ts";
import { selectTargetRoleRequest, targetRoleViewData } from "./target-role.ts";
import type { WorkflowStepControls } from "./workflow-route.tsx";
import type { WorkflowSnapshot } from "./workflow-state.ts";

export function TargetRoleStep({ snapshot, controls }: { snapshot: WorkflowSnapshot; controls: WorkflowStepControls }) {
  const exploration = snapshot.roleExploration;
  const [targetRole, setTargetRole] = useState<TargetRoleRead | null>(snapshot.targetRole);
  const [selecting, setSelecting] = useState<RoleCode | null>(null);
  const [error, setError] = useState("");
  const inFlight = useRef(false);
  const currentTarget = targetRoleViewData(
    targetRole && targetRole.role_exploration_id === exploration?.id ? targetRole : null,
  );
  const hasCurrentTarget = Boolean(currentTarget);
  const setNextReady = controls.setNextReady;

  useEffect(() => setTargetRole(snapshot.targetRole), [snapshot.targetRole]);
  useEffect(() => {
    setNextReady(hasCurrentTarget);
  }, [hasCurrentTarget, setNextReady]);

  async function chooseTargetRole(roleCode: RoleCode) {
    if (!snapshot.profile || !exploration || inFlight.current || controls.busy) return;
    inFlight.current = true;
    setSelecting(roleCode);
    setError("");
    try {
      const selected = await selectTargetRoleRequest(snapshot.profile.profile_id, roleCode, controls.apiUrl);
      setTargetRole(selected);
      await controls.refresh();
    } catch (selectionError) {
      setError(selectionError instanceof Error ? selectionError.message : "目标岗位保存失败，请重试。");
    } finally {
      inFlight.current = false;
      setSelecting(null);
    }
  }

  if (!exploration) return null;
  const disabled = selecting !== null || controls.busy;

  return (
    <div className="workflow-step-content">
      <div className="step-heading">
        <p className="section-kicker">Step 4 · Target Role</p>
        <h1 id="workflow-step-title">选择你的目标岗位</h1>
        <p className="summary">系统探索结果是参考；最终目标由你决定。你可以选择任一推荐等级中的岗位。</p>
      </div>
      <section className="target-selection-panel" aria-labelledby="system-exploration-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">系统探索结果</p>
            <h2 id="system-exploration-title">岗位方向参考</h2>
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
                <div className="role-card-list">
                  <strong>选择理由</strong>
                  <ul>{item.reasons.map((reason, index) => <li key={`${item.role_code}-reason-${index}`}>{reason}</li>)}</ul>
                </div>
                {item.concerns.length > 0 && (
                  <div className="role-card-list concern">
                    <strong>需要留意</strong>
                    <ul>{item.concerns.map((concern, index) => <li key={`${item.role_code}-concern-${index}`}>{concern}</li>)}</ul>
                  </div>
                )}
                <button type="button" className="target-role-button" disabled={disabled} onClick={() => void chooseTargetRole(item.role_code)}>
                  {selecting === item.role_code ? "保存中…" : selected ? "当前目标岗位" : "选择为目标岗位"}
                </button>
              </article>
            );
          })}
        </div>
        <p className="role-disclaimer">AI 推荐等级不等于你的最终选择。选择会保存为唯一的当前 Target Role。</p>
      </section>

      <section className="final-target-panel" aria-labelledby="final-target-title" aria-live="polite">
        <div>
          <p className="section-kicker">你的最终选择</p>
          <h2 id="final-target-title">{currentTarget?.role_name ?? "尚未选择目标岗位"}</h2>
        </div>
        {currentTarget && <span className="target-role-badge">由你选择</span>}
      </section>
      {error && <p className="message error" role="alert">{error}</p>}
    </div>
  );
}
