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
  { key: "ALL", label: "全部岗位" },
  { key: "READY", label: "简历已备" },
  { key: "TRACKER", label: "已入投递台" },
  { key: "INTERVIEW", label: "面试中" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

/** 投递状态是否已进入面试/Offer 阶段。 */
function isInterviewing(item: PlazaItem): boolean {
  const status = item.application_status as ApplicationStatus | null;
  return status === "INTERVIEW" || status === "OFFER";
}

/**
 * 行内状态标签：直接取真实投递状态，与行内小标签完全一致。
 * 之前用「阶段桶」把 PENDING 也渲染成「已投递」，导致同一张卡片
 * 右上角显示「已投递」、卡内小标签却写「待投递」的自相矛盾。
 */
function cardStatusLabel(item: PlazaItem): string {
  const status = item.application_status as ApplicationStatus | null;
  if (status) return APPLICATION_STATUS_LABEL[status] ?? status;
  return item.target_resume_confirmed ? "简历已备" : "准备中";
}

function cardStatusClass(item: PlazaItem): string {
  const status = item.application_status as ApplicationStatus | null;
  if (!status) return "muted";
  if (status === "CLOSED") return "attention";
  if (status === "PENDING") return "muted";
  return "filled";
}

function matchFilter(item: PlazaItem, filter: FilterKey): boolean {
  if (filter === "ALL") return true;
  if (filter === "READY") return item.target_resume_confirmed;
  if (filter === "TRACKER") return Boolean(item.application_id);
  if (filter === "INTERVIEW") return isInterviewing(item);
  return true;
}

function nextStatusLabel(status: ApplicationStatus | null): string {
  const current = status ?? "PENDING";
  const index = Math.min(APPLICATION_STATUS_ORDER.indexOf(current) + 1, APPLICATION_STATUS_ORDER.length - 1);
  return APPLICATION_STATUS_LABEL[APPLICATION_STATUS_ORDER[index]];
}

export function MissionsHome() {
  const [items, setItems] = useState<PlazaItem[]>([]);
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [query, setQuery] = useState("");
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

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return items.filter((item) => {
      if (!matchFilter(item, filter)) return false;
      if (!keyword) return true;
      return [item.role, item.company, item.location ?? ""]
        .join(" ")
        .toLowerCase()
        .includes(keyword);
    });
  }, [items, filter, query]);

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

  async function recede(item: PlazaItem) {
    if (!item.application_id) return;
    setBusyId(item.mission_id);
    setError("");
    try {
      const current = (item.application_status as ApplicationStatus) ?? "PENDING";
      const index = APPLICATION_STATUS_ORDER.indexOf(current);
      const prev = APPLICATION_STATUS_ORDER[Math.max(index - 1, 0)];
      await updateApplication(item.application_id, { status: prev });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "退回投递状态失败。");
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
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <section className="app-stat-grid" aria-label="岗位概览">
        <div className="app-stat-card"><div className="app-stat-value">{items.length}</div><div className="app-stat-label">岗位总数</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{items.filter((i) => i.target_resume_confirmed).length}</div><div className="app-stat-label">简历已备</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{items.filter((i) => i.application_id).length}</div><div className="app-stat-label">已入投递台</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{items.filter(isInterviewing).length}</div><div className="app-stat-label">面试中</div></div>
      </section>

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
            placeholder="搜索职位 / 公司 / 城市"
            aria-label="搜索职位、公司或城市"
          />
        </label>
        <select
          className="table-select"
          value={filter}
          onChange={(event) => setFilter(event.target.value as FilterKey)}
          aria-label="按准备度与投递状态筛选"
        >
          {FILTERS.map((f) => (
            <option key={f.key} value={f.key}>{f.label}</option>
          ))}
        </select>
      </div>

      <div className="table-actions">
        <Link className="app-btn primary" href="/missions/new">＋ 新建岗位</Link>
        <button type="button" className="app-btn" onClick={() => setShowBatch(true)}>批量导入</button>
      </div>

      {loading ? (
        <div className="app-empty">读取中…</div>
      ) : filtered.length ? (
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>职位</th>
                <th>公司</th>
                <th>城市</th>
                <th>投递状态</th>
                <th>准备度</th>
                <th style={{ textAlign: "right" }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const status = item.application_status as ApplicationStatus | null;
                const role = isUnknownIdentity(item.role) ? "未命名岗位" : item.role;
                const company = isUnknownIdentity(item.company) ? "" : item.company;
                const busy = busyId === item.mission_id;
                const target = `/missions/${encodeURIComponent(item.mission_id)}/role` as Route;
                return (
                  <tr key={item.mission_id}>
                    <td>
                      <div className="cell-title">
                        <Link href={target}>{role}</Link>
                        <div className="cell-tags">
                          {item.resume_ready
                            ? <span className="cell-tag">已绑定简历</span>
                            : <span className="cell-tag">简历待绑定</span>}
                          {item.target_resume_confirmed ? <span className="cell-tag strong">岗位版本已确认</span> : null}
                          {item.seniority ? <span className="cell-tag">{item.seniority}</span> : null}
                        </div>
                      </div>
                    </td>
                    <td>{company || <span className="cell-muted">—</span>}</td>
                    <td>{item.location || <span className="cell-muted">—</span>}</td>
                    <td><span className={`app-badge ${cardStatusClass(item)}`}>{cardStatusLabel(item)}</span></td>
                    <td>
                      <div className="cell-progress">
                        <div
                          className="cell-progress-bar"
                          role="progressbar"
                          aria-valuenow={item.prep_score}
                          aria-valuemin={0}
                          aria-valuemax={100}
                        >
                          <span style={{ width: `${item.prep_score}%` }} />
                        </div>
                        <span className="cell-progress-value">{item.prep_score}</span>
                      </div>
                    </td>
                    <td>
                      <div className="cell-actions">
                        {item.application_id ? (
                          <>
                            <button
                              type="button"
                              className="app-btn"
                              disabled={busy || (status ?? "PENDING") === "PENDING" || status === "CLOSED"}
                              title="退回上一个阶段"
                              onClick={() => void recede(item)}
                            >
                              ← 退回
                            </button>
                            <button
                              type="button"
                              className="app-btn primary"
                              disabled={busy}
                              onClick={() => void advance(item)}
                            >
                              {status === "CLOSED" ? "已结束" : `推进：${nextStatusLabel(status)}`}
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            className="app-btn primary"
                            disabled={busy}
                            onClick={() => void joinTracker(item)}
                          >
                            加入投递台
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="app-empty">
          {items.length
            ? "没有符合当前筛选条件的岗位，换个关键词或筛选试试。"
            : "还没有岗位。点「批量导入」一次粘贴多份 JD，或「新建岗位」逐个添加。"}
        </div>
      )}

      {showBatch ? <JobBatchImport onClose={() => setShowBatch(false)} onDone={() => { setShowBatch(false); void load(); }} /> : null}
    </main>
  );
}
