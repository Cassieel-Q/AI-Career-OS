"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  APPLICATION_CHANNELS,
  APPLICATION_STATUS_LABEL,
  APPLICATION_STATUS_ORDER,
  bindApplicationResume,
  createApplication,
  deleteApplication,
  fetchAllApplications,
  fetchApplicationBoard,
  generateApplicationGreeting,
  readCurrentProfileId,
  updateApplication,
  type ApplicationBoard,
  type ApplicationRead,
  type ApplicationStatus,
} from "../career-hub.ts";

function applicationBadgeClass(status: ApplicationStatus): string {
  if (status === "INTERVIEW" || status === "OFFER") return "filled";
  if (status === "CLOSED") return "attention";
  if (status === "PENDING") return "muted";
  return "filled";
}

function nextStatus(status: ApplicationStatus): ApplicationStatus | null {
  const index = APPLICATION_STATUS_ORDER.indexOf(status);
  if (index < 0 || index >= APPLICATION_STATUS_ORDER.length - 1) return null;
  return APPLICATION_STATUS_ORDER[index + 1];
}

/** 退回上一阶段；CLOSED 是终态，不允许再退回。 */
function prevStatus(status: ApplicationStatus): ApplicationStatus | null {
  if (status === "CLOSED") return null;
  const index = APPLICATION_STATUS_ORDER.indexOf(status);
  if (index <= 0) return null;
  return APPLICATION_STATUS_ORDER[index - 1];
}

export default function TrackerPage() {
  const [applications, setApplications] = useState<ApplicationRead[]>([]);
  const [board, setBoard] = useState<ApplicationBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyId, setBusyId] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ company: "", role: "", location: "", channel: "官网", status: "PENDING" as ApplicationStatus, next_action: "", jd_source: "" });
  // M3：筛选（状态 / 渠道 / 关键词）——只过滤展示，不改数据
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [filterChannel, setFilterChannel] = useState<string>("ALL");
  const [keyword, setKeyword] = useState("");
  // M3：打招呼话术编辑状态（application id → 草稿）
  const [greetingDraft, setGreetingDraft] = useState<Record<string, { short: string; long: string }>>({});
  const [greetingOpen, setGreetingOpen] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      // 全局读取：岗位可能挂在其它档案上，按当前档案查会漏记录。
      const appsData = await fetchAllApplications();
      setApplications(appsData.applications);
      const pid = readCurrentProfileId() || appsData.applications[0]?.profile_id || "";
      setBoard(pid ? await fetchApplicationBoard(pid) : null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取投递失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => applications.filter((app) => {
    if (filterStatus !== "ALL" && app.status !== filterStatus) return false;
    if (filterChannel !== "ALL" && app.channel !== filterChannel) return false;
    if (keyword.trim()) {
      const text = `${app.company} ${app.role} ${app.location ?? ""} ${app.notes ?? ""}`.toLowerCase();
      if (!text.includes(keyword.trim().toLowerCase())) return false;
    }
    return true;
  }), [applications, filterStatus, filterChannel, keyword]);

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
        jd_source: form.jd_source.trim() || null,
      });
      setShowForm(false);
      setForm({ company: "", role: "", location: "", channel: "官网", status: "PENDING", next_action: "", jd_source: "" });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建投递记录失败。");
    }
  }

  /** 绑定当前岗位最新已确认简历版本 + 生成 PDF 快照（回答「当初投的是哪份简历」）。 */
  async function bindResume(app: ApplicationRead) {
    setBusyId(app.id);
    setError("");
    setNotice("");
    try {
      await bindApplicationResume(app.id, { mission_id: app.mission_id });
      setNotice(`已绑定「${app.company} · ${app.role}」当前已确认的简历版本，并生成 PDF 快照。`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "绑定简历版本失败。");
    } finally {
      setBusyId("");
    }
  }

  /** 生成打招呼话术草稿（简洁版/详细版；只引用真实事实，不自动发送）。 */
  async function generateGreeting(app: ApplicationRead) {
    setBusyId(app.id);
    setError("");
    try {
      const updated = await generateApplicationGreeting(app.id);
      setGreetingDraft((prev) => ({
        ...prev,
        [app.id]: { short: updated.greeting_short ?? "", long: updated.greeting_long ?? "" },
      }));
      setGreetingOpen((prev) => ({ ...prev, [app.id]: true }));
      setApplications((prev) => prev.map((item) => (item.id === app.id ? updated : item)));
      setNotice("话术草稿已生成。可自由编辑后复制使用——系统不会自动发送。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "生成话术失败。");
    } finally {
      setBusyId("");
    }
  }

  async function saveGreeting(app: ApplicationRead) {
    const draft = greetingDraft[app.id];
    if (!draft) return;
    setBusyId(app.id);
    setError("");
    try {
      await updateApplication(app.id, { greeting_short: draft.short, greeting_long: draft.long });
      setNotice("话术已保存。");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存话术失败。");
    } finally {
      setBusyId("");
    }
  }

  function draftOf(app: ApplicationRead) {
    return greetingDraft[app.id] ?? { short: app.greeting_short ?? "", long: app.greeting_long ?? "" };
  }

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Tracker</p>
          <h1 className="app-page-title">投递</h1>
          <p className="app-page-subtitle">记录每一次投递动作：可推进/退回、绑定投出去的简历版本、生成打招呼话术，并沉淀面试问答。</p>
        </div>
        <button type="button" className="app-btn primary" onClick={() => setShowForm((v) => !v)}>
          {showForm ? "收起表单" : "新建投递记录"}
        </button>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}
      {notice ? <p className="message" role="status">{notice}</p> : null}

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
            <label className="field-label">JD 来源<input value={form.jd_source} onChange={(e) => setForm({ ...form, jd_source: e.target.value })} placeholder="JD 链接或「粘贴」（可选）" /></label>
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

      <section className="app-card" style={{ margin: "1rem 0" }} aria-label="筛选">
        <div className="tracker-filter-row">
          <label className="field-label">状态
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
              <option value="ALL">全部</option>
              {APPLICATION_STATUS_ORDER.map((s) => <option key={s} value={s}>{APPLICATION_STATUS_LABEL[s]}</option>)}
            </select>
          </label>
          <label className="field-label">渠道
            <select value={filterChannel} onChange={(e) => setFilterChannel(e.target.value)}>
              <option value="ALL">全部</option>
              {APPLICATION_CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="field-label">搜索
            <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="公司 / 岗位 / 备注" />
          </label>
        </div>
      </section>

      <h2 className="section-kicker" style={{ margin: "0 0 0.5rem" }}>投递记录{filtered.length !== applications.length ? `（筛选后 ${filtered.length}/${applications.length}）` : ""}</h2>
      {loading ? (
        <div className="app-empty">读取中…</div>
      ) : filtered.length ? (
        filtered.map((app) => {
          const next = nextStatus(app.status);
          const prev = prevStatus(app.status);
          const draft = draftOf(app);
          return (
            <div className="app-card" key={app.id} style={{ marginBottom: "0.9rem" }}>
              <div className="app-row">
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="app-card-title">{app.role}</div>
                  <div className="app-card-meta">
                    {app.company}
                    {app.location ? ` · ${app.location}` : ""}
                    {app.channel ? ` · ${app.channel}` : ""}
                    {app.next_action ? ` · 下一步：${app.next_action}` : ""}
                  </div>
                  <div className="app-card-meta">
                    {app.resume_version_id ? (
                      <>
                        投递版本：v{app.resume_version ?? "?"}（Studio 修订 r{app.studio_revision ?? "?"}）
                        {app.has_pdf_snapshot ? (
                          <a
                            href={`${process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8100"}/api/v1/applications/${app.id}/resume-snapshot`}
                            target="_blank"
                            rel="noreferrer"
                            style={{ marginLeft: "0.4rem" }}
                          >
                            下载投递快照
                          </a>
                        ) : null}
                      </>
                    ) : (
                      "尚未绑定简历版本"
                    )}
                  </div>
                </div>
                <span className={`app-badge ${applicationBadgeClass(app.status)}`}>{APPLICATION_STATUS_LABEL[app.status]}</span>
                <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                  <button type="button" className="app-btn" disabled={busyId === app.id || !app.mission_id || Boolean(app.resume_version_id)} title={app.mission_id ? "绑定当前已确认的简历版本并生成 PDF 快照" : "该记录未关联岗位"} onClick={() => void bindResume(app)}>
                    绑定简历版本
                  </button>
                  <button type="button" className="app-btn" disabled={busyId === app.id} onClick={() => setGreetingOpen((prevMap) => ({ ...prevMap, [app.id]: !prevMap[app.id] }))}>
                    {greetingOpen[app.id] ? "收起话术" : "打招呼话术"}
                  </button>
                  <button
                    type="button"
                    className="app-btn"
                    disabled={busyId === app.id || !prev}
                    title={prev ? `退回至「${APPLICATION_STATUS_LABEL[prev]}」` : "已在最初阶段"}
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
                  <Link className="app-btn" href={`/interview-records/new?company=${encodeURIComponent(app.company)}` as Route} title="记录这家公司的面试问题与回答">
                    记面试问答
                  </Link>
                  <button type="button" className="app-btn danger" disabled={busyId === app.id} onClick={() => void remove(app)}>
                    删除
                  </button>
                </div>
              </div>

              {greetingOpen[app.id] ? (
                <div style={{ marginTop: "0.75rem", borderTop: "1px solid var(--border)", paddingTop: "0.75rem", display: "grid", gap: "0.6rem" }}>
                  <div className="app-chip-note">话术草稿只引用简历与 JD 里真实存在的内容；复制后自己去招聘平台粘贴，系统不会自动发送。</div>
                  {!app.greeting_short && !draft.short ? (
                    <button type="button" className="app-btn primary" disabled={busyId === app.id} onClick={() => void generateGreeting(app)}>
                      生成话术草稿
                    </button>
                  ) : null}
                  <label className="field-label">
                    简洁版（打招呼弹窗直接粘贴）
                    <textarea value={draft.short} rows={3} onChange={(e) => setGreetingDraft((prevMap) => ({ ...prevMap, [app.id]: { ...draft, short: e.target.value } }))} />
                  </label>
                  <div style={{ display: "flex", gap: "0.4rem" }}>
                    <button type="button" className="app-btn" onClick={() => void navigator.clipboard?.writeText(draft.short)}>复制简洁版</button>
                  </div>
                  <label className="field-label">
                    详细版（站内信 / 邮件正文）
                    <textarea value={draft.long} rows={5} onChange={(e) => setGreetingDraft((prevMap) => ({ ...prevMap, [app.id]: { ...draft, long: e.target.value } }))} />
                  </label>
                  <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                    <button type="button" className="app-btn" onClick={() => void navigator.clipboard?.writeText(draft.long)}>复制详细版</button>
                    <button type="button" className="app-btn primary" disabled={busyId === app.id} onClick={() => void saveGreeting(app)}>保存话术</button>
                    <button type="button" className="app-btn" disabled={busyId === app.id} onClick={() => void generateGreeting(app)}>重新生成</button>
                  </div>
                </div>
              ) : null}
            </div>
          );
        })
      ) : (
        <div className="app-empty" style={{ marginBottom: "1.5rem" }}>还没有投递记录。点击右上角「新建投递记录」，或到「岗位」页「加入投递台」。</div>
      )}

      {board ? (
        <>
          <h2 className="section-kicker" style={{ margin: "1.25rem 0 0.5rem" }}>求职看板</h2>
          <section className="app-stat-grid" aria-label="阶段数量">
            {APPLICATION_STATUS_ORDER.map((status) => (
              <div className="app-stat-card" key={status}>
                <div className="app-stat-value">{board.columns[status]?.count ?? 0}</div>
                <div className="app-stat-label">{APPLICATION_STATUS_LABEL[status]}</div>
              </div>
            ))}
          </section>
          <div style={{ display: "grid", gap: "0.9rem", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", margin: "0.9rem 0 1.5rem" }}>
            <section className="app-card">
              <h3 className="app-card-title">简历版本使用记录</h3>
              {board.version_usage.length ? (
                board.version_usage.map((usage) => (
                  <div key={usage.resume_version_id} style={{ marginBottom: "0.6rem" }}>
                    <div className="app-card-meta">
                      简历 v{usage.resume_version ?? "?"}（Studio r{usage.studio_revision ?? "?"}）投过 {usage.used_by.length} 个岗位
                    </div>
                    {usage.used_by.map((used) => (
                      <div className="app-card-meta" key={used.application_id} style={{ paddingLeft: "0.8rem" }}>
                        · {used.company} · {used.role}（{APPLICATION_STATUS_LABEL[used.status as ApplicationStatus] ?? used.status}）
                      </div>
                    ))}
                  </div>
                ))
              ) : (
                <div className="app-card-meta">还没有投递绑定简历版本。在投递记录里点「绑定简历版本」。</div>
              )}
            </section>
            <section className="app-card">
              <h3 className="app-card-title">最近面试</h3>
              {board.recent_interviews.length ? (
                board.recent_interviews.map((item) => (
                  <div className="app-card-meta" key={item.id}>
                    · {item.company} {item.interview_round ? `· ${item.interview_round}` : ""} {item.interviewed_on ? `· ${item.interviewed_on}` : ""}
                  </div>
                ))
              ) : (
                <div className="app-card-meta">还没有面试记录。</div>
              )}
            </section>
            <section className="app-card">
              <h3 className="app-card-title">待办提醒</h3>
              {board.reminders.length ? (
                board.reminders.map((item) => (
                  <div className="app-card-meta" key={item.id}>
                    · {item.title} {item.due_at ? `· ${item.due_at.slice(0, 16).replace("T", " ")}` : ""}
                  </div>
                ))
              ) : (
                <div className="app-card-meta">暂无待办提醒。</div>
              )}
              <div className="app-chip-note" style={{ marginTop: "0.5rem" }}>{board.reminder_note}</div>
            </section>
          </div>
        </>
      ) : null}
    </main>
  );
}
