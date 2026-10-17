"use client";

/**
 * BOSS 投递准备包（M3）
 * 岗位详情 → 匹配 → 定向简历 → Studio → PDF → 打招呼话术 → 打开原岗位 → 记录投递。
 *
 * 硬边界（UI 层同样遵守）：
 * - 话术只展示后端生成/用户编辑的内容，前端不拼接任何未确认的事实；
 * - 只有「复制」和「打开原岗位」，没有任何自动发送、自动投递；
 * - 投递快照链接指向的是绑定时生成的固定 PDF。
 */
import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import { MISSION_API_BASE_URL } from "./missions.ts";

export type BossKit = {
  mission: { id: string; company: string; role: string; location: string | null; workflow_state: string };
  source_url: string | null;
  resume: { version_id: string | null; version: number | null; confirmed: boolean; studio_url: string };
  application: {
    id: string;
    status: string;
    stage: string;
    greeting_short: string | null;
    greeting_long: string | null;
    has_pdf_snapshot: boolean;
    resume_version: number | null;
    studio_revision: number | null;
  } | null;
  greeting: { short: string; long: string } | null;
  snapshot_url: string | null;
  can_open_original: boolean;
};

const STAGE_LABEL: Record<string, string> = {
  PREPARING: "准备中",
  APPLIED: "已投递",
  INTERVIEW: "面试中",
  COMPLETED: "已结束",
  ARCHIVED: "已归档",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${MISSION_API_BASE_URL}${path}`, init);
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      /* keep code */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function readBossKit(missionId: string): Promise<BossKit> {
  return api(`/api/v1/missions/${encodeURIComponent(missionId)}/boss-kit`);
}

export function generateBossGreeting(missionId: string): Promise<{
  application_id: string;
  short: string;
  long: string;
  grounded_on: Record<string, unknown>;
  note: string;
}> {
  return api(`/api/v1/missions/${encodeURIComponent(missionId)}/boss-kit/greeting`, { method: "POST" });
}

export function saveBossGreeting(
  missionId: string,
  body: { short?: string; long?: string },
): Promise<{ application_id: string; short: string; long: string }> {
  return api(`/api/v1/missions/${encodeURIComponent(missionId)}/boss-kit/greeting`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function markBossApplied(missionId: string): Promise<{ application: BossKit["application"]; warning: string | null; note: string }> {
  return api(`/api/v1/missions/${encodeURIComponent(missionId)}/boss-kit/mark-applied`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ channel: "BOSS 直聘", bind_resume: true }),
  });
}

export function createBossReminder(missionId: string, title?: string): Promise<{ id: string; title: string; due_at: string | null }> {
  return api(`/api/v1/missions/${encodeURIComponent(missionId)}/boss-kit/reminder`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
}

export function BossKitPanel({ missionId }: { missionId: string }) {
  const [kit, setKit] = useState<BossKit | null>(null);
  const [short, setShort] = useState("");
  const [long, setLong] = useState("");
  const [busy, setBusy] = useState<"" | "greeting" | "save" | "applied" | "reminder">("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    try {
      const data = await readBossKit(missionId);
      setKit(data);
      setShort(data.greeting?.short ?? "");
      setLong(data.greeting?.long ?? "");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取投递准备信息失败。");
    }
  }, [missionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const generate = useCallback(async () => {
    setBusy("greeting");
    setError("");
    setNotice("");
    try {
      const result = await generateBossGreeting(missionId);
      setShort(result.short);
      setLong(result.long);
      setNotice(result.note);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成话术失败。");
    } finally {
      setBusy("");
    }
  }, [load, missionId]);

  const saveGreeting = useCallback(async () => {
    setBusy("save");
    setError("");
    try {
      await saveBossGreeting(missionId, { short, long });
      setNotice("话术已保存（可继续编辑，不会被自动生成覆盖）。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存话术失败。");
    } finally {
      setBusy("");
    }
  }, [long, missionId, short]);

  const markApplied = useCallback(async () => {
    setBusy("applied");
    setError("");
    try {
      const result = await markBossApplied(missionId);
      setNotice(result.warning ? `${result.note} ${result.warning}` : result.note);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "标记已投递失败。");
    } finally {
      setBusy("");
    }
  }, [load, missionId]);

  const addReminder = useCallback(async () => {
    setBusy("reminder");
    setError("");
    try {
      const result = await createBossReminder(missionId);
      setNotice(`已创建跟进提醒：${result.title}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建提醒失败。");
    } finally {
      setBusy("");
    }
  }, [missionId]);

  if (!kit) {
    return (
      <section className="mission-card">
        <p className="section-kicker">BOSS 投递准备</p>
        <p className="summary">{error || "正在读取投递准备信息…"}</p>
      </section>
    );
  }

  const stage = kit.application?.stage ?? "PREPARING";

  return (
    <section className="mission-card">
      <div className="section-heading">
        <div>
          <p className="section-kicker">BOSS 投递准备</p>
          <h3>
            话术 · 岗位版简历 · 投递记录
            {kit.application ? <span className="app-badge filled" style={{ marginLeft: "0.5rem" }}>{STAGE_LABEL[stage] ?? stage}</span> : null}
          </h3>
        </div>
      </div>

      <div className="mission-action-row">
        <button type="button" className="app-btn primary" disabled={busy === "greeting"} onClick={() => void generate()}>
          {busy === "greeting" ? "生成中…" : "生成 BOSS 打招呼"}
        </button>
        {kit.can_open_original && kit.source_url ? (
          <a className="app-btn" href={kit.source_url} target="_blank" rel="noreferrer">
            打开原岗位 ↗
          </a>
        ) : (
          <span className="app-muted" title="这个岗位没有记录原始链接（例如手动粘贴时没带地址）">
            无原始链接
          </span>
        )}
        <Link className="app-btn" href={`/missions/${encodeURIComponent(missionId)}/resume/studio` as Route}>
          打开岗位版简历
        </Link>
        <button type="button" className="app-btn" disabled={busy === "applied"} onClick={() => void markApplied()}>
          {busy === "applied" ? "处理中…" : "标记已投递"}
        </button>
        {kit.application?.has_pdf_snapshot && kit.snapshot_url ? (
          <a className="app-btn" href={`${MISSION_API_BASE_URL}${kit.snapshot_url}`} target="_blank" rel="noreferrer">
            下载投递快照 PDF
          </a>
        ) : null}
        <button type="button" className="app-btn" disabled={busy === "reminder"} onClick={() => void addReminder()}>
          {busy === "reminder" ? "创建中…" : "创建跟进提醒"}
        </button>
      </div>

      <p className="summary">
        岗位版简历：
        {kit.resume.confirmed
          ? `已确认第 ${kit.resume.version ?? "—"} 版（Studio 修订 ${kit.application?.studio_revision ?? "—"}）`
          : "还没有已确认的岗位版简历，标记已投递时不会生成 PDF 快照"}
      </p>

      <div className="mission-original-jd">
        <p className="section-kicker">简洁版（适合 BOSS 打招呼弹窗，可直接复制）</p>
        <textarea
          rows={3}
          value={short}
          onChange={(event) => setShort(event.target.value)}
          placeholder="点「生成 BOSS 打招呼」后这里会出现草稿，可自由编辑。"
        />
        <div className="mission-action-row">
          <button type="button" className="app-btn" onClick={() => void navigator.clipboard?.writeText(short)}>
            复制简洁版
          </button>
        </div>
      </div>

      <div className="mission-original-jd">
        <p className="section-kicker">详细版（适合站内信 / 邮件正文）</p>
        <textarea
          rows={6}
          value={long}
          onChange={(event) => setLong(event.target.value)}
          placeholder="点「生成 BOSS 打招呼」后这里会出现草稿，可自由编辑。"
        />
        <div className="mission-action-row">
          <button type="button" className="app-btn" onClick={() => void navigator.clipboard?.writeText(long)}>
            复制详细版
          </button>
        </div>
      </div>

      <div className="mission-action-row">
        <button type="button" className="app-btn primary" disabled={busy === "save" || !short} onClick={() => void saveGreeting()}>
          {busy === "save" ? "保存中…" : "保存话术到这条岗位"}
        </button>
        <span className="app-muted">话术只引用你已确认的真实经历；系统不会自动发送，也不会自动投递。</span>
      </div>

      {notice ? <p className="summary">{notice}</p> : null}
      {error ? <p className="app-inline-error">{error}</p> : null}
    </section>
  );
}
