"use client";

import { useCallback, useEffect, useState } from "react";

import {
  APPLICATION_CHANNELS,
  APPLICATION_STATUS_LABEL,
  APPLICATION_STATUS_ORDER,
  createApplication,
  deleteApplication,
  fetchApplications,
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

export default function TrackerPage() {
  const [applications, setApplications] = useState<ApplicationRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ company: "", role: "", location: "", channel: "官网", status: "PENDING" as ApplicationStatus, next_action: "" });

  const load = useCallback(async () => {
    const pid = readCurrentProfileId();
    if (!pid) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      const appsData = await fetchApplications(pid);
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

  async function advance(app: ApplicationRead) {
    setBusyId(app.id);
    setError("");
    try {
      const index = APPLICATION_STATUS_ORDER.indexOf(app.status);
      const next = APPLICATION_STATUS_ORDER[Math.min(index + 1, APPLICATION_STATUS_ORDER.length - 1)];
      await updateApplication(app.id, { status: next });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "推进状态失败。");
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
    const pid = readCurrentProfileId();
    if (!pid || !form.company.trim() || !form.role.trim()) {
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
          <p className="app-page-subtitle">记录每一次投递动作，推进状态，跟踪面试与结果。</p>
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
        <div className="app-stat-card"><div className="app-stat-value">{applications.length}</div><div className="app-stat-label">投递记录</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{applications.filter((a) => a.status === "PENDING").length}</div><div className="app-stat-label">待投递</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{applications.filter((a) => ["APPLIED", "SCREENING", "ASSESSMENT"].includes(a.status)).length}</div><div className="app-stat-label">已投递</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{applications.filter((a) => ["INTERVIEW", "OFFER"].includes(a.status)).length}</div><div className="app-stat-label">面试 / Offer</div></div>
      </section>

      <h2 className="section-kicker" style={{ margin: "0 0 0.5rem" }}>投递记录</h2>
      {loading ? (
        <div className="app-empty">读取中…</div>
      ) : applications.length ? (
        applications.map((app) => (
          <div className="app-card app-row" key={app.id}>
            <div style={{ flex: 1 }}>
              <div className="app-card-title">{app.role}</div>
              <div className="app-card-meta">
                {app.company}
                {app.location ? ` · ${app.location}` : ""}
                {app.channel ? ` · ${app.channel}` : ""}
                {app.next_action ? ` · 下一步：${app.next_action}` : ""}
              </div>
            </div>
            <span className={`app-badge ${applicationBadgeClass(app.status)}`}>{APPLICATION_STATUS_LABEL[app.status]}</span>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {app.status !== "CLOSED" ? (
                <button type="button" className="app-btn" disabled={busyId === app.id} onClick={() => void advance(app)}>
                  推进
                </button>
              ) : null}
              <button type="button" className="app-btn danger" disabled={busyId === app.id} onClick={() => void remove(app)}>
                删除
              </button>
            </div>
          </div>
        ))
      ) : (
        <div className="app-empty" style={{ marginBottom: "1.5rem" }}>还没有投递记录。点击右上角「新建投递记录」，或从岗位页「加入投递台」。</div>
      )}
    </main>
  );
}
