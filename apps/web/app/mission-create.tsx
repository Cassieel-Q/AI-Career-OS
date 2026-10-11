"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { createDraftProfile, createMission, PROFILE_STORAGE_KEY } from "./missions.ts";
import { humanizeMissionError } from "./mission-state.ts";
import { upsertProfileLabel } from "./profile-label.ts";
import { MISSION_COPY } from "./mission-copy.ts";
import { TaskProgress } from "./task-progress.tsx";
import { withTaskTimeout } from "./task-progress.ts";
import { readMission } from "./missions.ts";

export function MissionCreate({ profileId: initialProfileId }: { profileId?: string }) {
  const [rawText, setRawText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [taskStage, setTaskStage] = useState<number | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rawText.trim().length < 20) {
      setError("请粘贴完整一些的岗位描述。");
      return;
    }
    setBusy(true);
    setError("");
    setTaskStage(0);
    try {
      let profileId = (initialProfileId || window.localStorage.getItem(PROFILE_STORAGE_KEY) || "").trim();
      if (!profileId) {
        const draft = await createDraftProfile();
        profileId = draft.profile_id;
        window.localStorage.setItem(PROFILE_STORAGE_KEY, profileId);
        upsertProfileLabel(profileId, "档案", "fallback");
      } else {
        // Keep registry in sync when preparing with an existing profile id.
        upsertProfileLabel(profileId, "档案", "fallback");
      }
      const mission = await withTaskTimeout(createMission(profileId, rawText.trim(), sourceUrl.trim() || null), 120_000, "岗位识别");
      setTaskStage(1);
      await withTaskTimeout(readMission(mission.id), 30_000, "岗位信息读取");
      // 产品流：分析完成后落到岗位理解（ROLE_UNDERSTOOD）页
      window.location.assign(`/missions/${encodeURIComponent(mission.id)}/role`);
    } catch (caught) {
      setError(humanizeMissionError(caught instanceof Error ? caught.message : "", "jd_analysis"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mission-home">
      <header className="workflow-header">
        <Link className="button-secondary" href="/missions">← 岗位档案</Link>
      </header>
      <section className="mission-home-content">
        <p className="eyebrow">岗位档案</p>
        <h1>{MISSION_COPY.addRoleTitle}</h1>
        <p className="summary">{MISSION_COPY.addRoleDescription}</p>
        <form className="mission-card mission-form" onSubmit={submit}>
          <label className="field-label">
            粘贴岗位描述（JD）
            <textarea
              value={rawText}
              onChange={(event) => setRawText(event.target.value)}
              rows={18}
              minLength={20}
              required
              placeholder="把完整 JD 粘贴在这里…"
            />
          </label>
          <label className="field-label">
            来源链接（可选）
            <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} type="url" />
          </label>
          {error && (
            <p className="message error" role="alert">
              {error}
            </p>
          )}
          {taskStage !== null && <TaskProgress kind="jd" activeIndex={taskStage} error={error} onRetry={() => document.querySelector<HTMLFormElement>(".mission-form")?.requestSubmit()} />}
          <div className="mission-action-row">
            <button type="submit" className="mission-primary-cta" disabled={busy || rawText.trim().length < 20}>
              {busy ? "正在识别岗位信息…" : error ? "重新识别" : MISSION_COPY.identifyRole}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
