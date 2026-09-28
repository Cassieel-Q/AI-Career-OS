"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { JobDescriptionsSection } from "./job-descriptions-section.tsx";
import { MINIMUM_JOB_DESCRIPTIONS, jobDescriptionReadiness } from "./job-descriptions.ts";
import { createMarketProfileRequest } from "./market-profile.ts";
import type { WorkflowStepControls } from "./workflow-route.tsx";
import type { WorkflowSnapshot } from "./workflow-state.ts";
import { runSingleFlight } from "./workflow-actions.ts";

export function JobDescriptionsStep({ profileId, snapshot, controls }: { profileId: string; snapshot: WorkflowSnapshot; controls: WorkflowStepControls }) {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef<Promise<boolean> | null>(null);
  const targetRole = snapshot.targetRole;
  const records = targetRole ? snapshot.jobDescriptions.filter((record) => record.target_role_id === targetRole.id) : [];
  const ready = jobDescriptionReadiness(records.length).ready;
  const generate = useCallback(() => runSingleFlight(generation, async () => {
    if (!targetRole || records.length < MINIMUM_JOB_DESCRIPTIONS) return false;
    setLoading(true);
    setError("");
    try {
      await createMarketProfileRequest(targetRole.id, controls.apiUrl);
      await controls.refresh();
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "市场画像暂时生成失败，请重试。");
      return false;
    } finally {
      setLoading(false);
    }
  }), [controls, records.length, targetRole]);
  const generateAndNavigate = useCallback(async () => {
    if (await generate()) router.push(`/workflow/${profileId}/market-profile`);
  }, [generate, profileId, router]);
  useEffect(() => {
    controls.setNextReady(ready);
    controls.setNextAction(ready ? generate : null);
    return () => controls.setNextAction(null);
  }, [controls, generate, ready]);

  if (!targetRole) return null;
  return <div className="workflow-step-content">
    <div className="step-heading">
      <p className="section-kicker">Step 4 · Job Descriptions</p>
      <h1 id="workflow-step-title">为当前目标岗位建立真实市场样本</h1>
      <p className="summary">粘贴真实招聘描述。每个样本保留原文，并绑定到你当前选择的目标岗位。</p>
    </div>
    {error && <div className="workflow-inline-error" role="alert"><p>{error}</p><button type="button" className="button-secondary" onClick={() => void generateAndNavigate()}>重试</button></div>}
    <JobDescriptionsSection
      key={targetRole.id}
      targetRole={targetRole}
      apiUrl={controls.apiUrl}
      initialRecords={records}
      onPersistedChange={controls.refresh}
    />
    <div className="workflow-callout">
      <p>{ready ? "已达到 3 条 JD。生成市场画像后会直接进入能力维度分析。" : `还需要 ${Math.max(0, MINIMUM_JOB_DESCRIPTIONS - records.length)} 条 JD 才能生成市场画像。`}</p>
      <button type="button" disabled={!ready || loading} onClick={() => void generateAndNavigate()}>{loading ? "正在生成市场画像…" : "生成市场画像"}</button>
    </div>
  </div>;
}
