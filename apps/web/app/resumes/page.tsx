"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchResumesOverview, readCurrentProfileId, type ResumesOverviewRead } from "../career-hub.ts";
import { isUnknownIdentity } from "../mission-state.ts";

const FILTERS = [
  { key: "ALL", label: "全部版本" },
  { key: "CONFIRMED", label: "已确认" },
  { key: "DRAFT", label: "草稿" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

export default function ResumesPage() {
  const [profileId] = useState<string>(readCurrentProfileId());
  const [overview, setOverview] = useState<ResumesOverviewRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [query, setQuery] = useState("");

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
      setError(caught instanceof Error ? caught.message : "读取简历失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return (overview?.resumes ?? []).filter((resume) => {
      if (filter === "CONFIRMED" && !resume.confirmed) return false;
      if (filter === "DRAFT" && resume.confirmed) return false;
      if (!keyword) return true;
      return [resume.role, resume.company].join(" ").toLowerCase().includes(keyword);
    });
  }, [overview, filter, query]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Resumes</p>
          <h1 className="app-page-title">简历</h1>
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
      ) : !overview?.resumes.length ? (
        <div className="app-empty">还没有简历版本。进入某个岗位完成简历策略后，版本会出现在这里。</div>
      ) : (
        <>
          <div className="table-toolbar">
            <label className="table-search">
              <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <circle cx="7" cy="7" r="4.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
                <path d="M10.5 10.5 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索岗位 / 公司"
                aria-label="搜索岗位或公司"
              />
            </label>
            <select
              className="table-select"
              value={filter}
              onChange={(event) => setFilter(event.target.value as FilterKey)}
              aria-label="按确认状态筛选"
            >
              {FILTERS.map((f) => (
                <option key={f.key} value={f.key}>{f.label}</option>
              ))}
            </select>
          </div>

          {filtered.length ? (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>岗位</th>
                    <th>公司</th>
                    <th>版本</th>
                    <th>要点数</th>
                    <th>更新时间</th>
                    <th>状态</th>
                    <th style={{ textAlign: "right" }}>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((resume) => (
                    <tr key={resume.resume_id}>
                      <td>
                        <div className="cell-title">
                          <Link href={`/missions/${encodeURIComponent(resume.mission_id)}/resume/studio` as Route}>
                            {isUnknownIdentity(resume.role) ? "未命名岗位" : resume.role}
                          </Link>
                        </div>
                      </td>
                      <td>{isUnknownIdentity(resume.company) ? <span className="cell-muted">—</span> : resume.company}</td>
                      <td>v{resume.version}</td>
                      <td>{resume.bullet_count} 条</td>
                      <td>
                        <span className="cell-muted">
                          {resume.updated_at ? new Date(resume.updated_at).toLocaleDateString("zh-CN") : "—"}
                        </span>
                      </td>
                      <td>
                        <span className={`app-badge ${resume.confirmed ? "filled" : "muted"}`}>
                          {resume.confirmed ? "已确认" : "草稿"}
                        </span>
                      </td>
                      <td>
                        <div className="cell-actions">
                          <Link
                            className="app-btn"
                            href={`/missions/${encodeURIComponent(resume.mission_id)}/resume/studio` as Route}
                          >
                            打开工作台
                          </Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="app-empty">没有符合当前筛选条件的简历版本。</div>
          )}
        </>
      )}
    </main>
  );
}
