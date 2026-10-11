"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import { fetchResumesOverview, fetchTracker, readCurrentProfileId, STAGE_LABEL, stageBadgeClass, type TrackerRead } from "./career-hub.ts";
import { isUnknownIdentity } from "./mission-state.ts";

/** 求职路径四步：一条横向前进的流程，而非功能入口堆叠。 */
const FLOW: Array<{ key: string; title: string; desc: string; href: Route }> = [
  { key: "find", title: "找岗位", desc: "明确目标与 JD", href: "/missions" },
  { key: "write", title: "写简历", desc: "岗位定向版本", href: "/resumes" },
  { key: "track", title: "投递跟进", desc: "记录每一家进度", href: "/tracker" },
  { key: "interview", title: "面试复盘", desc: "沉淀真实面试", href: "/interview-records" },
];

export default function HomePage() {
  const [profileId, setProfileId] = useState<string>("");
  const [tracker, setTracker] = useState<TrackerRead | null>(null);
  const [resumeCount, setResumeCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const pid = readCurrentProfileId();
    if (!pid) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const [track, resumes] = await Promise.all([fetchTracker(pid), fetchResumesOverview(pid)]);
      setTracker(track);
      setResumeCount(resumes.total);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取概览失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setProfileId(readCurrentProfileId());
    void load();
  }, [load]);

  const recent = tracker?.applications.slice(0, 5) ?? [];

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Overview</p>
          <h1 className="app-page-title">求职工作台</h1>
          <p className="app-page-subtitle">从目标岗位到 offer，一条清晰的路径。</p>
        </div>
        {profileId ? (
          <span className="app-badge muted" title={profileId}>档案已就绪</span>
        ) : null}
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <section aria-label="求职路径" style={{ marginBottom: "1.75rem" }}>
        <div className="app-flow">
          {FLOW.map((step, index) => (
            <Link key={step.key} className="app-flow-step" href={step.href}>
              <span className="app-flow-index">{index + 1}</span>
              <span className="app-flow-title">{step.title}</span>
              <span className="app-flow-desc">{step.desc}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="app-stat-grid" aria-label="数据概览">
        <div className="app-stat-card">
          <div className="app-stat-value">{tracker?.total ?? 0}</div>
          <div className="app-stat-label">目标岗位</div>
        </div>
        <div className="app-stat-card">
          <div className="app-stat-value">{resumeCount}</div>
          <div className="app-stat-label">简历版本</div>
        </div>
        <div className="app-stat-card">
          <div className="app-stat-value">{tracker?.applied ?? 0}</div>
          <div className="app-stat-label">已投递</div>
        </div>
        <div className="app-stat-card">
          <div className="app-stat-value">{tracker?.interviewing ?? 0}</div>
          <div className="app-stat-label">面试中</div>
        </div>
      </section>

      <section aria-label="最近岗位">
        <h2 className="app-card-title" style={{ margin: "0 0 0.75rem" }}>最近岗位</h2>
        {loading ? (
          <div className="app-empty">读取中…</div>
        ) : recent.length ? (
          recent.map((item) => (
            <Link
              key={item.mission_id}
              className="app-card app-row"
              href={`/missions/${encodeURIComponent(item.mission_id)}/role` as Route}
            >
              <div>
                <div className="app-card-title">
                  {isUnknownIdentity(item.role) ? "未命名岗位" : item.role}
                </div>
                <div className="app-card-meta">
                  {isUnknownIdentity(item.company) ? "" : `${item.company} · `}
                  {item.location || "地点未定"}
                </div>
              </div>
              <span className={`app-badge ${stageBadgeClass(item.stage)}`}>{STAGE_LABEL[item.stage]}</span>
            </Link>
          ))
        ) : (
          <div className="app-empty">
            还没有岗位档案。
            <Link className="app-btn primary" href="/missions/new" style={{ marginLeft: "0.75rem" }}>
              新建岗位
            </Link>
          </div>
        )}
      </section>
    </main>
  );
}
