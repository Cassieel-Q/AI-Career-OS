"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  APPLICATION_CHANNELS,
  APPLICATION_STATUS_LABEL,
  APPLICATION_STATUS_ORDER,
  createApplication,
  deleteApplication,
  fetchAllApplications,
  readCurrentProfileId,
  updateApplication,
  type ApplicationRead,
  type ApplicationStatus,
} from "../career-hub.ts";

function applicationBadgeClass(status: ApplicationStatus): string {
  if (status === "INTERVIEW" || status === "OFFER") return "filled";
  if (status === "CLOSED") return "attention";
  if (status === "PENDING") return "muted";
  return "filled";
}

function prevStatus(status: ApplicationStatus): ApplicationStatus | null {
  const index = APPLICATION_STATUS_ORDER.indexOf(status);
  if (index <= 0) return null;
  return APPLICATION_STATUS_ORDER[index - 1];
}

function nextStatus(status: ApplicationStatus): ApplicationStatus | null {
  const index = APPLICATION_STATUS_ORDER.indexOf(status);
  if (index < 0 || index >= APPLICATION_STATUS_ORDER.length - 1) return null;
  return APPLICATION_STATUS_ORDER[index + 1];
}

export default function TrackerPage() {
  const [applications, setApplications] = useState<ApplicationRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ company: "", role: "", location: "", channel: "官网", status: "PENDING" as ApplicationStatus, next_action: "" });

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // 全局读取：岗位可能挂在其它档案上，按当前档案查会漏记录。
      const appsData = await fetchAllApplications();
      setApplications(appsData.applications);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取投递失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const stats = useMemo(() => ({
    total: applications.length,
    pending: applications.filter((a) => a.status === "PENDING").length,
    applied: applications.filter((a) => ["APPLIED", "SCREENING", "ASSESSMENT"].includes(a.status)).length,
    interview: applications.filter((a) => ["INTERVIEW", "OFFER"].includes(a.status)).length,
  }), [applications]);

  async function setStatus(app: ApplicationRead, status: ApplicationStatus) {
    setBusyId(app.id);
    setError("");
    try {
      await updateApplication(app.id, { status });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "更新状态失败。");
    } finally {
      setBusyId("");
    }
  }

  async function remove(app: ApplicationRead) {
    if (!window.confirm(`删除「${app.company} · ${app.role}」的投递记录？`)) return;
    setBusyId(app.id);
    setError("");
    try {
      await deleteApplication(app.id);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除失败。");
    } finally {
      setBusyId("");
    }
  }

  async function submitForm() {
    // 优先用当前档案；没有就复用已有记录所属的档案（本地单用户场景）。
    const pid = readCurrentProfileId() || applications[0]?.profile_id || "";
    if (!pid) {
      setError("还没有简历档案。请先到「简历」页上传一份简历，再新建投递记录。");
      return;
    }
    if (!form.company.trim() || !form.role.trim()) {
      setError("请填写公司和岗位。");
      return;
    }
    setError("");
    try {
      await createApplication(pid, {
        company: form.company.trim(),
        role: form.role.trim(),
        location: form.location.trim() || null,
        channel: form.channel,
        status: form.status,
        next_action: form.next_action.trim() || null,
      });
      setShowForm(false);
      setForm({ company: "", role: "", location: "", channel: "官网", status: "PENDING", next_action: "" });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建投递记录失败。");
    }
  }

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Tracker</p>
          <h1 className="app-page-title">投递</h1>
          <p className="app-page-subtitle">记录每一次投递动作，逐级推进或退回状态，并沉淀面试问答。</p>
        </div>
        <button type="button" className="app-btn primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "收起表单" : "新建投递记录"}
        </button>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      {showForm ? (
        <section className="app-card" style={{ marginBottom: "1.25rem" }}>
          <h3 className="app-card-title">新建投递记录</h3>
          <div className="tracker-form-grid">
            <label className="field-label">公司<input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} placeholder="公司名" /></label>
            <label className="field-label">岗位<input value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} placeholder="岗位名" /></label>
            <label className="field-label">地点<input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="城市（可选）" /></label>
            <label className="field-label">渠道<select value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>{APPLICATION_CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}</select></label>
            <label className="field-label">状态<select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as ApplicationStatus })}>{APPLICATION_STATUS_ORDER.map((s) => <option key={s} value={s}>{APPLICATION_STATUS_LABEL[s]}</option>)}</select></label>
            <label className="field-label">下一步动作<input value={form.next_action} onChange={(e) => setForm({ ...form, next_action: e.target.value })} placeholder="如：下周一跟进 HR（可选）" /></label>
          </div>
          <div className="mission-action-row" style={{ marginTop: "0.75rem" }}>
            <button type="button" className="app-btn primary" onClick={() => void submitForm()}>保存记录</button>
            <button type="button" className="app-btn" onClick={() => setShowForm(false)}>取消</button>
          </div>
        </section>
      ) : null}

      <section className="app-stat-grid" aria-label="投递概览">
        <div className="app-stat-card"><div className="app-stat-value">{stats.total}</div><div className="app-stat-label">投递记录</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{stats.pending}</div><div className="app-stat-label">待投递</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{stats.applied}</div><div className="app-stat-label">已投递</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{stats.interview}</div><div className="app-stat-label">面试 / Offer</div></div>
      </section>

      <h2 className="section-kicker" style={{ margin: "0 0 0.5rem" }}>投递记录</h2>
      {loading ? (
        <div className="app-empty">读取中…</div>
      ) : applications.length ? (
        applications.map((app) => {
          const prev = prevStatus(app.status);
          const next = nextStatus(app.status);
          return (
            <div className="app-card app-row" key={app.id}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="app-card-title">{app.role}</div>
                <div className="app-card-meta">
                  {app.company}
                  {app.location ? ` · ${app.location}` : ""}
                  {app.channel ? ` · ${app.channel}` : ""}
                  {app.next_action ? ` · 下一步：${app.next_action}` : ""}
                </div>
              </div>
              <span className={`app-badge ${applicationBadgeClass(app.status)}`}>{APPLICATION_STATUS_LABEL[app.status]}</span>
              <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="app-btn"
                  disabled={busyId === app.id || !prev}
                  title={prev ? `退回至「${APPLICATION_STATUS_LABEL[prev]}」` : "已在最前阶段"}
                  onClick={() => prev && void setStatus(app, prev)}
                >
                  ← 退回
                </button>
                <button
                  type="button"
                  className="app-btn primary"
                  disabled={busyId === app.id || !next}
                  title={next ? `推进至「${APPLICATION_STATUS_LABEL[next]}」` : "已到最后阶段"}
                  onClick={() => next && void setStatus(app, next)}
                >
                  推进 →
                </button>
                <Link
                  className="app-btn"
                  href={`/interview-records/new?company=${encodeURIComponent(app.company)}` as Route}
                  title="记录这家公司的面试问题与回答"
                >
                  记面试问答
                </Link>
                <button type="button" className="app-btn danger" disabled={busyId === app.id} onClick={() => void remove(app)}>
                  删除
                </button>
              </div>
            </div>
          );
        })
      ) : (
        <div className="app-empty" style={{ marginBottom: "1.5rem" }}>还没有投递记录。点击右上角「新建投递记录」，或到「岗位」页「加入投递台」。</div>
      )}
    </main>
  );
}
