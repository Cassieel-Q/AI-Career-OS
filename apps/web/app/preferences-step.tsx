"use client";

import { useCallback, useEffect, useState } from "react";

import {
  CAREER_PREFERENCE_OPTIONS,
  careerPreferencesDraftFromProfile,
  isCareerPreferencesDraftValid,
  saveCareerPreferencesRequest,
  toggleCareerPreference,
} from "./career-preferences.ts";
import type { CareerPreferencePriority, CareerPreferencesDraft } from "./career-preferences.ts";
import type { Profile } from "./profile-flow.ts";
import type { WorkflowNextAction, WorkflowStepControls } from "./workflow-route.tsx";

export function PreferencesStep({ profile, controls }: { profile: Profile; controls: WorkflowStepControls }) {
  const [draft, setDraft] = useState<CareerPreferencesDraft>(() => careerPreferencesDraftFromProfile(profile));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const valid = isCareerPreferencesDraftValid(draft.priority_order, draft.weekly_hours);
  const setNextReady = controls.setNextReady;
  const setNextAction = controls.setNextAction;

  useEffect(() => {
    setDraft(careerPreferencesDraftFromProfile(profile));
  }, [profile]);

  useEffect(() => {
    setNextReady(valid);
  }, [setNextReady, valid]);

  const saveAndContinue = useCallback<WorkflowNextAction>(async () => {
    if (!isCareerPreferencesDraftValid(draft.priority_order, draft.weekly_hours)) {
      setError("请选择两个不同的职业偏好，并填写 1–60 小时。");
      return false;
    }
    setSaving(true);
    setError("");
    try {
      const preferences = await saveCareerPreferencesRequest(profile.profile_id, draft, controls.apiUrl);
      setDraft(careerPreferencesDraftFromProfile({ ...profile, preferences }));
      return true;
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "职业偏好保存失败，请重试。");
      return false;
    } finally {
      setSaving(false);
    }
  }, [controls.apiUrl, draft, profile]);

  useEffect(() => {
    setNextAction(saveAndContinue);
    return () => setNextAction(null);
  }, [setNextAction, saveAndContinue]);

  const disabled = saving || controls.busy;

  function changePriority(value: CareerPreferencePriority) {
    setDraft((current) => ({
      ...current,
      priority_order: toggleCareerPreference(current.priority_order, value),
    }));
    setError("");
  }

  return (
    <div className="workflow-step-content">
      <div className="step-heading">
        <p className="section-kicker">Step 2 · Career Preferences</p>
        <h1 id="workflow-step-title">你现在更看重什么？</h1>
        <p className="summary">选择两项并排出先后顺序，再告诉我们你每周可投入多少时间。</p>
      </div>
      <section className="career-preferences preference-step" aria-label="Career Preferences">
        <h2>你的两项优先考虑</h2>
        <div className="preference-grid">
          {CAREER_PREFERENCE_OPTIONS.map((option) => {
            const order = draft.priority_order.indexOf(option.value);
            const selected = order !== -1;
            const full = draft.priority_order.length >= 2;
            return (
              <button
                key={option.value}
                type="button"
                className={selected ? "preference-card selected" : "preference-card"}
                aria-pressed={selected}
                disabled={disabled || (full && !selected)}
                onClick={() => changePriority(option.value)}
              >
                <span className="preference-order">{selected ? `第 ${order + 1} 优先` : "未选择"}</span>
                <span>{option.label}</span>
              </button>
            );
          })}
        </div>
        <p className="profile-note">已选择 {draft.priority_order.length} / 2 项。点击已选项目可移除，再选择另一项调整优先级。</p>
        <label className="field-label">
          每周可用于职业准备 / 学习的时间（小时）
          <input
            type="number"
            min={1}
            max={60}
            step={1}
            value={draft.weekly_hours}
            disabled={disabled}
            aria-describedby="weekly-hours-guidance"
            onChange={(event) => {
              setDraft((current) => ({ ...current, weekly_hours: event.target.value }));
              setError("");
            }}
          />
        </label>
        <p id="weekly-hours-guidance" className="profile-note">填写 1–60 小时的整数。下一步会先保存你的选择。</p>
        {error && <p className="message error" role="alert">{error}</p>}
      </section>
    </div>
  );
}
