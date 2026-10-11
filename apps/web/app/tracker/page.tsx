"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useState } from "react";

import { fetchTracker, readCurrentProfileId, STAGE_LABEL, stageBadgeClass, type TrackerRead } from "../career-hub.ts";
import { isUnknownIdentity } from "../mission-state.ts";

const FILTERS = [
  { key: "ALL", label: "全部" },
  { key: "PREPARING", label: "准备中" },
  { key: "APPLIED", label: "已投递" },
  { key: "INTERVIEW", label: "面试中" },
  { key: "COMPLETED", label: "已结束" },
] as const;

export default function TrackerPage() {
  const [profileId] = useState<string>(readCurrentProfileId());
  const [tracker, setTracker] = useState<TrackerRead | null>(null);
  const [filter, setFilter] = useState<string>("ALL");
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
      setTracker(await fetchTracker(pid));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取求职进度失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const applications = useMemo(() => {
    const all = tracker?.applications ?? [];
    if (filter === "ALL") return all;
    return all.filter((item) => item.stage === filter);
  }, [tracker, filter]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Tracker</p>
          <h1 className="app-page-title">求职进度</h1>
          <p className="app-page-subtitle">一家公司一条记录，跟踪投递、面试与结果。</p>
        </div>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <section className="app-stat-grid" aria-label="进度概览">
        <div className="app-stat-card"><div className="app-stat-value">{tracker?.total ?? 0}</div><div className="app-stat-label">总岗位</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{tracker?.preparing ?? 0}</div><div className="app-stat-label">准备中</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{tracker?.applied ?? 0}</div><div className="app-stat-label">已投递</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{tracker?.interviewing ?? 0}</div><div className="app-stat-label">面试中</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{tracker?.completed ?? 0}</div><div className="app-stat-label">已结束</div></div>
      </section>

      <div className="app-filter-row" role="tablist" aria-label="按阶段筛选">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            type="button"
            role="tab"
            aria-selected={filter === f.key}
            className={`app-filter${filter === f.key ? " active" : ""}`}
            onClick={() => setFilter(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="app-empty">读取中…</div>
      ) : !profileId ? (
        <div className="app-empty">
          还没有简历档案。请先
          <Link className="app-btn primary" href="/workflow/start" style={{ margin: "0 0.5rem" }}>上传简历</Link>
          或
          <Link className="app-btn" href="/missions/new" style={{ marginLeft: "0.5rem" }}>新建岗位</Link>
        </div>
      ) : applications.length ? (
        applications.map((item) => (
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
                {item.resume_ready ? " · 简历已备" : " · 简历待备"}
                {item.outcome_status ? ` · ${item.outcome_status}` : ""}
              </div>
            </div>
            <span className={`app-badge ${stageBadgeClass(item.stage)}`}>{STAGE_LABEL[item.stage]}</span>
          </Link>
        ))
      ) : (
        <div className="app-empty">当前筛选下没有岗位。</div>
      )}
    </main>
  );
}
