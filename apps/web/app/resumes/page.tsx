"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import { fetchResumesOverview, readCurrentProfileId, type ResumesOverviewRead } from "../career-hub.ts";
import { isUnknownIdentity } from "../mission-state.ts";

export default function ResumesPage() {
  const [profileId] = useState<string>(readCurrentProfileId());
  const [overview, setOverview] = useState<ResumesOverviewRead | null>(null);
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
      setOverview(await fetchResumesOverview(pid));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取简历中心失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Resumes</p>
          <h1 className="app-page-title">简历中心</h1>
          <p className="app-page-subtitle">每个岗位的定向简历版本集中管理。</p>
        </div>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <section className="app-stat-grid" aria-label="简历概览">
        <div className="app-stat-card"><div className="app-stat-value">{overview?.total ?? 0}</div><div className="app-stat-label">简历版本</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{overview?.resumes.filter((r) => r.confirmed).length ?? 0}</div><div className="app-stat-label">已确认</div></div>
      </section>

      {loading ? (
        <div className="app-empty">读取中…</div>
      ) : !profileId ? (
        <div className="app-empty">
          还没有简历档案。请先
          <Link className="app-btn primary" href="/workflow/start" style={{ margin: "0 0.5rem" }}>上传简历</Link>
        </div>
      ) : overview?.resumes.length ? (
        overview.resumes.map((resume) => (
          <Link
            key={resume.resume_id}
            className="app-card app-row"
            href={`/missions/${encodeURIComponent(resume.mission_id)}/resume/studio` as Route}
          >
            <div>
              <div className="app-card-title">
                {isUnknownIdentity(resume.role) ? "未命名岗位" : resume.role}
                <span className="resume-version"> · v{resume.version}</span>
              </div>
              <div className="app-card-meta">
                {isUnknownIdentity(resume.company) ? "" : `${resume.company} · `}
                {resume.bullet_count} 条要点
                {resume.updated_at ? ` · 更新于 ${new Date(resume.updated_at).toLocaleDateString("zh-CN")}` : ""}
              </div>
            </div>
            <span className={`app-badge ${resume.confirmed ? "filled" : "muted"}`}>
              {resume.confirmed ? "已确认" : "草稿"}
            </span>
          </Link>
        ))
      ) : (
        <div className="app-empty">还没有简历版本。进入某个岗位完成简历策略后，版本会出现在这里。</div>
      )}
    </main>
  );
}
