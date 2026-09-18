"use client";

import { useEffect, useRef, useState } from "react";

import {
  MAXIMUM_JOB_DESCRIPTIONS,
  addJobDescriptionToCollection,
  canAddJobDescription,
  createJobDescriptionRequest,
  deleteJobDescriptionRequest,
  getJobDescriptionsRequest,
  jobDescriptionReadiness,
  normalizeJobDescriptionSourceUrl,
  removeJobDescriptionFromCollection,
  updateJobDescriptionInCollection,
  updateJobDescriptionRequest,
} from "./job-descriptions";
import type { JobDescriptionPatch, JobDescriptionRead } from "./job-descriptions";
import type { TargetRoleRead } from "./target-role";


type Draft = { raw_text: string; source_url: string };

function draftFrom(record: JobDescriptionRead): Draft {
  return { raw_text: record.raw_text, source_url: record.source_url ?? "" };
}

export function JobDescriptionsSection({
  targetRole,
  apiUrl,
  disabled = false,
}: {
  targetRole: TargetRoleRead;
  apiUrl: string;
  disabled?: boolean;
}) {
  const [records, setRecords] = useState<JobDescriptionRead[]>([]);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [newDraft, setNewDraft] = useState<Draft>({ raw_text: "", source_url: "" });
  const [showNew, setShowNew] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const requestToken = useRef(0);

  useEffect(() => {
    let active = true;
    const token = ++requestToken.current;
    setLoading(true);
    setError("");
    void getJobDescriptionsRequest(targetRole.id, apiUrl)
      .then((loaded) => {
        if (!active || token !== requestToken.current) return;
        setRecords(loaded);
        setDrafts(Object.fromEntries(loaded.map((record) => [record.id, draftFrom(record)])));
      })
      .catch((loadError) => {
        if (active && token === requestToken.current) {
          setError(loadError instanceof Error ? loadError.message : "岗位样本加载失败。请重试。");
        }
      })
      .finally(() => {
        if (active && token === requestToken.current) setLoading(false);
      });
    return () => {
      active = false;
      requestToken.current += 1;
    };
  }, [apiUrl, targetRole.id]);

  const busy = disabled || pendingId !== null;
  const readiness = jobDescriptionReadiness(records.length);

  async function createRecord() {
    if (busy || !newDraft.raw_text.trim() || !canAddJobDescription(records.length)) return;
    setPendingId("new");
    setError("");
    try {
      const created = await createJobDescriptionRequest(targetRole.id, newDraft, apiUrl);
      setRecords((current) => addJobDescriptionToCollection(current, created));
      setDrafts((current) => ({ ...current, [created.id]: draftFrom(created) }));
      setNewDraft({ raw_text: "", source_url: "" });
      setShowNew(false);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "岗位样本保存失败。请重试。");
    } finally {
      setPendingId(null);
    }
  }

  async function updateRecord(record: JobDescriptionRead) {
    const draft = drafts[record.id] ?? draftFrom(record);
    if (busy || !draft.raw_text.trim()) return;
    const payload: JobDescriptionPatch = {};
    if (draft.raw_text !== record.raw_text) payload.raw_text = draft.raw_text;
    const nextUrl = normalizeJobDescriptionSourceUrl(draft.source_url);
    if (nextUrl !== record.source_url) payload.source_url = nextUrl;
    if (Object.keys(payload).length === 0) return;
    setPendingId(record.id);
    setError("");
    try {
      const updated = await updateJobDescriptionRequest(record.id, payload, apiUrl);
      setRecords((current) => updateJobDescriptionInCollection(current, updated));
      setDrafts((current) => ({ ...current, [updated.id]: draftFrom(updated) }));
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "岗位样本更新失败。请重试。");
    } finally {
      setPendingId(null);
    }
  }

  async function deleteRecord(record: JobDescriptionRead) {
    if (busy) return;
    setPendingId(record.id);
    setError("");
    try {
      await deleteJobDescriptionRequest(record.id, apiUrl);
      setRecords((current) => removeJobDescriptionFromCollection(current, record.id));
      setDrafts((current) => {
        const next = { ...current };
        delete next[record.id];
        return next;
      });
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "岗位样本删除失败。请重试。");
    } finally {
      setPendingId(null);
    }
  }

  function updateDraft(id: string, field: keyof Draft, value: string) {
    setDrafts((current) => ({
      ...current,
      [id]: { ...(current[id] ?? { raw_text: "", source_url: "" }), [field]: value },
    }));
  }

  return (
    <section className="job-descriptions" aria-label="Real job description samples">
      <div className="section-heading jd-heading">
        <div>
          <p className="section-kicker">当前目标岗位</p>
          <h3>{targetRole.role_name}</h3>
        </div>
        <strong className="jd-count">{records.length} / {MAXIMUM_JOB_DESCRIPTIONS}</strong>
      </div>
      <p className="profile-note">建议添加 5–10 个真实 JD，至少 3 个后再进行市场要求分析。</p>
      {error && <p className="message error" role="alert">{error}</p>}
      {loading ? <p className="profile-note">正在加载已保存的岗位样本...</p> : (
        <>
          <div className="jd-list">
            {records.map((record, index) => {
              const draft = drafts[record.id] ?? draftFrom(record);
              const changed = draft.raw_text !== record.raw_text || normalizeJobDescriptionSourceUrl(draft.source_url) !== record.source_url;
              return (
                <article className="jd-card" key={record.id}>
                  <h4>JD #{index + 1}</h4>
                  <label className="field-label">
                    岗位描述原文
                    <textarea rows={8} value={draft.raw_text} disabled={busy} onChange={(event) => updateDraft(record.id, "raw_text", event.target.value)} />
                  </label>
                  <label className="field-label">
                    来源链接（可选）
                    <input type="url" value={draft.source_url} disabled={busy} placeholder="https://..." onChange={(event) => updateDraft(record.id, "source_url", event.target.value)} />
                  </label>
                  <div className="jd-actions">
                    <button type="button" disabled={busy || !draft.raw_text.trim() || !changed} onClick={() => void updateRecord(record)}>
                      {pendingId === record.id ? "保存中..." : "保存修改"}
                    </button>
                    <button type="button" className="delete-button" disabled={busy} onClick={() => void deleteRecord(record)}>删除</button>
                  </div>
                </article>
              );
            })}
            {showNew && (
              <article className="jd-card jd-card-new">
                <h4>新 JD</h4>
                <label className="field-label">
                  岗位描述原文
                  <textarea rows={8} autoFocus value={newDraft.raw_text} disabled={busy} onChange={(event) => setNewDraft((current) => ({ ...current, raw_text: event.target.value }))} />
                </label>
                <label className="field-label">
                  来源链接（可选）
                  <input type="url" value={newDraft.source_url} disabled={busy} placeholder="https://..." onChange={(event) => setNewDraft((current) => ({ ...current, source_url: event.target.value }))} />
                </label>
                <div className="jd-actions">
                  <button type="button" disabled={busy || !newDraft.raw_text.trim()} onClick={() => void createRecord()}>{pendingId === "new" ? "保存中..." : "保存 JD"}</button>
                  <button type="button" className="button-secondary" disabled={busy} onClick={() => { setShowNew(false); setNewDraft({ raw_text: "", source_url: "" }); }}>取消</button>
                </div>
              </article>
            )}
          </div>
          {!showNew && (
            <button type="button" className="button-secondary jd-add" disabled={busy || !canAddJobDescription(records.length)} onClick={() => setShowNew(true)}>
              {canAddJobDescription(records.length) ? "+ 添加一个 JD" : "已达到 10 个 JD 上限"}
            </button>
          )}
          <div className={`jd-readiness ${readiness.ready ? "ready" : ""}`} aria-live="polite">
            {readiness.ready ? "✓ 已达到最低分析要求" : `还需添加 ${readiness.remaining} 个 JD 才达到最低分析要求`}
          </div>
          <div className={`jd-next-step ${readiness.ready ? "ready" : ""}`} aria-disabled={!readiness.ready}>下一步：分析市场要求</div>
        </>
      )}
    </section>
  );
}
