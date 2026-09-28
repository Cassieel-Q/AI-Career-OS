"use client";

import Link from "next/link";
import { useState } from "react";
import type { FormEvent } from "react";

import { createDraftProfile, createMission, PROFILE_STORAGE_KEY } from "./missions.ts";
import { humanizeMissionError } from "./mission-state.ts";
import { upsertProfileLabel } from "./profile-label.ts";

export function MissionCreate({ profileId: initialProfileId }: { profileId?: string }) {
  const [rawText, setRawText] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (rawText.trim().length < 20) {
      setError("请粘贴完整一些的岗位描述。");
      return;
    }
    setBusy(true);
    setError("");
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
      const mission = await createMission(profileId, rawText.trim(), sourceUrl.trim() || null);
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
        <Link className="workflow-brand" href="/missions">
          <span className="workflow-brand-mark" aria-hidden="true">A</span>
          <span>AI Career OS</span>
        </Link>
        <Link className="button-secondary" href="/missions">← 我的岗位</Link>
      </header>
      <section className="mission-home-content">
        <p className="eyebrow">准备一个新岗位</p>
        <h1>你想准备哪个岗位？</h1>
        <p className="summary">只需要粘贴岗位描述。公司、岗位、级别和要求会自动识别，识别后你可以确认或修改。</p>
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
          <div className="mission-action-row">
            <button type="submit" className="mission-primary-cta" disabled={busy || rawText.trim().length < 20}>
              {busy ? "正在分析岗位…" : "分析这个岗位"}
            </button>
          </div>
        </form>
      </section>
    </main>
  );
}
