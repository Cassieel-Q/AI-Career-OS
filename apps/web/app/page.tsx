"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import { fetchOverview, readCurrentProfileId, STAGE_LABEL, stageBadgeClass, type OverviewRead } from "./career-hub.ts";
import ModelOnboarding from "./model-onboarding.tsx";
import { AFTER_APPLY_LINKS, nextStepFor } from "./home-next-step.ts";
import { isUnknownIdentity } from "./mission-state.ts";

/** 其它能力：保留全部功能，但作为次级入口，不抢首次使用的注意力。 */
const FLOW: Array<{ key: string; title: string; desc: string; href: Route }> = [
  { key: "find", title: "找岗位", desc: "明确目标与 JD", href: "/missions" },
  { key: "write", title: "写简历", desc: "岗位定向版本", href: "/resumes" },
  { key: "track", title: "投递跟进", desc: "记录每一家进度", href: "/tracker" },
  { key: "interview", title: "面试题库", desc: "按公司场次准备", href: "/question-bank" },
];

export default function HomePage() {
  const [profileId, setProfileId] = useState<string>("");
  const [overview, setOverview] = useState<OverviewRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // 总览统一走全局接口：四个数字与「岗位 / 简历 / 投递」各页保持同一口径。
  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setOverview(await fetchOverview());
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

  const totals = overview?.totals;
  const recent = overview?.recent_missions ?? [];
  const nextStep = nextStepFor({
    hasProfile: Boolean(profileId),
    missionCount: totals?.missions ?? 0,
    resumeCount: totals?.resumes ?? 0,
    appliedCount: totals?.applied ?? 0,
    latestMissionId: recent[0]?.mission_id ?? null,
  });

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

      <ModelOnboarding
        hasProfile={Boolean(profileId)}
        missionCount={overview?.totals?.missions ?? 0}
        resumeCount={overview?.totals?.resumes ?? 0}
      />

      {/* 主线：一次只突出一个动作（导入简历 → 添加岗位 → 审阅并导出 → 按投递版准备面试） */}
      <section className="app-card home-next-step" aria-label="下一步">
        <p className="section-kicker">下一步</p>
        <h2 className="app-card-title">{nextStep.title}</h2>
        <p className="summary">{nextStep.desc}</p>
        <div className="home-next-step-actions">
          <Link className="app-btn primary" href={nextStep.href as Route}>
            {nextStep.action}
          </Link>
          {nextStep.key === "AFTER_APPLY"
            ? AFTER_APPLY_LINKS.map((item) => (
                <Link key={item.href} className="app-btn" href={item.href as Route}>
                  {item.label}
                </Link>
              ))
            : null}
        </div>
      </section>

      <section aria-label="其它能力" style={{ marginBottom: "1.75rem" }}>
        <p className="section-kicker" style={{ marginBottom: "0.5rem" }}>其它能力</p>
        <div className="app-flow">
          {FLOW.map((step) => (
            <Link key={step.key} className="app-flow-step" href={step.href}>
              <span className="app-flow-title">{step.title}</span>
              <span className="app-flow-desc">{step.desc}</span>
            </Link>
          ))}
        </div>
      </section>

      <section className="app-stat-grid" aria-label="数据概览">
        <div className="app-stat-card">
          <div className="app-stat-value">{totals?.missions ?? 0}</div>
          <div className="app-stat-label">目标岗位</div>
        </div>
        <div className="app-stat-card">
          <div className="app-stat-value">{totals?.resumes ?? 0}</div>
          <div className="app-stat-label">简历版本</div>
        </div>
        <div className="app-stat-card">
          <div className="app-stat-value">{totals?.applied ?? 0}</div>
          <div className="app-stat-label">已投递</div>
        </div>
        <div className="app-stat-card">
          <div className="app-stat-value">{totals?.interviewing ?? 0}</div>
          <div className="app-stat-label">面试中</div>
        </div>
      </section>

      <p className="app-card-meta" style={{ margin: "-0.75rem 0 1.25rem" }}>
        以上为全部档案的合计；投递记录共 {totals?.applications ?? 0} 条，可在「投递」页查看明细。
      </p>

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
