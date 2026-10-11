"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  APPLICATION_STATUS_LABEL,
  APPLICATION_STATUS_ORDER,
  createApplication,
  fetchPlaza,
  readCurrentProfileId,
  updateApplication,
  type ApplicationStatus,
  type PlazaItem,
} from "./career-hub.ts";
import { isUnknownIdentity } from "./mission-state.ts";
import { JobBatchImport } from "./job-batch-import.tsx";

const FILTERS = [
  { key: "ALL", label: "全部" },
  { key: "READY", label: "简历已备" },
  { key: "APPLIED", label: "已投递" },
  { key: "INTERVIEW", label: "面试中" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

function stageOf(item: PlazaItem): string {
  const status = item.application_status as ApplicationStatus | null;
  if (!status) return "PREPARING";
  if (status === "CLOSED") return "CLOSED";
  if (status === "INTERVIEW" || status === "OFFER") return "INTERVIEW";
  return "APPLIED";
}

function matchFilter(item: PlazaItem, filter: FilterKey): boolean {
  if (filter === "ALL") return true;
  if (filter === "READY") return item.target_resume_confirmed;
  const stage = stageOf(item);
  if (filter === "APPLIED") return stage === "APPLIED";
  if (filter === "INTERVIEW") return stage === "INTERVIEW";
  return true;
}

function badgeClass(stage: string): string {
  if (stage === "INTERVIEW" || stage === "APPLIED") return "filled";
  if (stage === "CLOSED") return "attention";
  return "muted";
}

function stageLabel(stage: string): string {
  if (stage === "APPLIED") return "已投递";
  if (stage === "INTERVIEW") return "面试中";
  if (stage === "CLOSED") return "已结束";
  return "准备中";
}

export function MissionsHome() {
  const [items, setItems] = useState<PlazaItem[]>([]);
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [showBatch, setShowBatch] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const plaza = await fetchPlaza();
      setItems(plaza.items);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取岗位失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => items.filter((item) => matchFilter(item, filter)), [items, filter]);

  async function joinTracker(item: PlazaItem) {
    setBusyId(item.mission_id);
    setError("");
    try {
      const profileId = item.profile_id || readCurrentProfileId();
      if (!profileId) {
        setError("还没有简历档案，无法建立投递记录。");
        return;
      }
      await createApplication(profileId, {
        mission_id: item.mission_id,
        company: item.company,
        role: item.role,
        location: item.location,
        status: "PENDING",
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "加入投递台失败。");
    } finally {
      setBusyId("");
    }
  }

  async function advance(item: PlazaItem) {
    if (!item.application_id) return;
    setBusyId(item.mission_id);
    setError("");
    try {
      const current = (item.application_status as ApplicationStatus) ?? "PENDING";
      const index = APPLICATION_STATUS_ORDER.indexOf(current);
      const next = APPLICATION_STATUS_ORDER[Math.min(index + 1, APPLICATION_STATUS_ORDER.length - 1)];
      await updateApplication(item.application_id, { status: next });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "推进投递状态失败。");
    } finally {
      setBusyId("");
    }
  }

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Jobs</p>
          <h1 className="app-page-title">岗位</h1>
          <p className="app-page-subtitle">集中浏览与批量导入目标岗位，按准备度与投递状态统一管理。</p>
        </div>
        <div className="mission-home-actions" style={{ margin: 0 }}>
          <button type="button" className="app-btn" onClick={() => setShowBatch(true)}>
            批量导入
          </button>
          <Link className="app-btn primary" href="/missions/new">
            新建岗位
          </Link>
        </div>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <section className="app-stat-grid" aria-label="岗位概览">
        <div className="app-stat-card"><div className="app-stat-value">{items.length}</div><div className="app-stat-label">岗位总数</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{items.filter((i) => i.target_resume_confirmed).length}</div><div className="app-stat-label">简历已备</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{items.filter((i) => i.application_id).length}</div><div className="app-stat-label">已入投递台</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{items.filter((i) => stageOf(i) === "INTERVIEW").length}</div><div className="app-stat-label">面试中</div></div>
      </section>

      <div className="app-filter-row" role="tablist" aria-label="按状态筛选">
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
      ) : filtered.length ? (
        <div className="plaza-grid">
          {filtered.map((item) => {
            const stage = stageOf(item);
            const status = item.application_status as ApplicationStatus | null;
            const role = isUnknownIdentity(item.role) ? "未命名岗位" : item.role;
            const company = isUnknownIdentity(item.company) ? "" : item.company;
            return (
              <article className="plaza-card" key={item.mission_id}>
                <div className="plaza-card-head">
                  <div>
                    <h3 className="plaza-card-title">{role}</h3>
                    <p className="plaza-card-company">
                      {company}
                      {item.location ? ` · ${item.location}` : ""}
                    </p>
                  </div>
                  <span className={`app-badge ${badgeClass(stage)}`}>{stageLabel(stage)}</span>
                </div>

                <div className="plaza-progress-row">
                  <span className="plaza-progress-label">准备度</span>
                  <div className="plaza-progress" role="progressbar" aria-valuenow={item.prep_score} aria-valuemin={0} aria-valuemax={100}>
                    <span style={{ width: `${item.prep_score}%` }} />
                  </div>
                  <span className="plaza-progress-value">{item.prep_score}</span>
                </div>

                <div className="plaza-tags">
                  {item.resume_ready ? <span className="plaza-tag">已绑定简历</span> : <span className="plaza-tag muted">简历待绑定</span>}
                  {item.target_resume_confirmed ? <span className="plaza-tag">岗位版本已确认</span> : null}
                  {status ? <span className="plaza-tag status">{APPLICATION_STATUS_LABEL[status]}</span> : null}
                </div>

                <div className="plaza-card-actions">
                  <Link className="app-btn" href={`/missions/${encodeURIComponent(item.mission_id)}/role` as Route}>
                    进入岗位
                  </Link>
                  {item.application_id ? (
                    <button
                      type="button"
                      className="app-btn primary"
                      disabled={busyId === item.mission_id}
                      onClick={() => void advance(item)}
                    >
                      {status === "CLOSED" ? "已结束" : `推进：${APPLICATION_STATUS_LABEL[APPLICATION_STATUS_ORDER[Math.min(APPLICATION_STATUS_ORDER.indexOf(status ?? "PENDING") + 1, APPLICATION_STATUS_ORDER.length - 1)]]}`}
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="app-btn primary"
                      disabled={busyId === item.mission_id}
                      onClick={() => void joinTracker(item)}
                    >
                      加入投递台
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="app-empty">
          还没有岗位。点「批量导入」一次粘贴多份 JD，或「新建岗位」逐个添加。
        </div>
      )}

      {showBatch ? <JobBatchImport onClose={() => setShowBatch(false)} onDone={() => { setShowBatch(false); void load(); }} /> : null}
    </main>
  );
}
