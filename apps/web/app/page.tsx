"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import { fetchResumesOverview, fetchTracker, readCurrentProfileId, STAGE_LABEL, stageBadgeClass, type TrackerRead } from "./career-hub.ts";
import { isUnknownIdentity } from "./mission-state.ts";

const QUICK_LINKS: Array<{ key: string; title: string; desc: string; href: Route }> = [
  { key: "jobs", title: "找岗位", desc: "管理目标岗位与 JD", href: "/missions" },
  { key: "resume", title: "做简历", desc: "查看岗位定向简历版本", href: "/resumes" },
  { key: "track", title: "投递跟进", desc: "求职进度一目了然", href: "/tracker" },
  { key: "interview", title: "面试准备", desc: "面试记录与复盘", href: "/interview-records" },
];

export default function HomePage() {
  const [profileId] = useState<string>(readCurrentProfileId());
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
    void load();
  }, [load]);

  const recent = tracker?.applications.slice(0, 5) ?? [];

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Overview</p>
          <h1 className="app-page-title">首页</h1>
          <p className="app-page-subtitle">从看岗位到拿 offer，每一步都在这里。</p>
        </div>
        {profileId ? (
          <span className="app-badge muted" title={profileId}>当前档案已就绪</span>
        ) : null}
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

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

      <section aria-label="快捷入口">
        <h2 className="app-card-title" style={{ margin: "0 0 0.75rem" }}>开始使用</h2>
        <div className="app-stat-grid">
          {QUICK_LINKS.map((link) => (
            <Link key={link.key} className="app-card app-quick-link" href={link.href}>
              <span className="app-card-title">{link.title}</span>
              <span className="app-card-meta">{link.desc}</span>
            </Link>
          ))}
        </div>
      </section>

      <section aria-label="最近岗位" style={{ marginTop: "1.5rem" }}>
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
