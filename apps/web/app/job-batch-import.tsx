"use client";

import { useState } from "react";
import type { BulkCreateResult, JobDraft } from "./career-hub.ts";
import { bulkCreateMissions, parseJobBatch } from "./career-hub.ts";
import { createDraftProfile } from "./missions.ts";
import { PROFILE_STORAGE_KEY } from "./missions.ts";

type Props = {
  onClose: () => void;
  onDone: () => void;
};

export function JobBatchImport({ onClose, onDone }: Props) {
  const [rawText, setRawText] = useState("");
  const [drafts, setDrafts] = useState<JobDraft[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<BulkCreateResult | null>(null);

  async function parse() {
    if (rawText.trim().length < 20) {
      setError("请先粘贴至少一段完整的岗位描述。");
      return;
    }
    setBusy(true);
    setError("");
    setResult(null);
    try {
      let profileId = window.localStorage.getItem(PROFILE_STORAGE_KEY)?.trim() || "";
      if (!profileId) {
        const draft = await createDraftProfile();
        profileId = draft.profile_id;
        window.localStorage.setItem(PROFILE_STORAGE_KEY, profileId);
      }
      const list = await parseJobBatch(profileId, rawText.trim());
      setDrafts(list);
      setSelected(new Set(list.map((_, i) => i)));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "识别失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  function toggle(i: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  async function save() {
    if (!drafts) return;
    const chosen = drafts.filter((_, i) => selected.has(i));
    if (!chosen.length) {
      setError("请至少勾选一个岗位。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      let profileId = window.localStorage.getItem(PROFILE_STORAGE_KEY)?.trim() || "";
      if (!profileId) {
        const draft = await createDraftProfile();
        profileId = draft.profile_id;
        window.localStorage.setItem(PROFILE_STORAGE_KEY, profileId);
      }
      const res = await bulkCreateMissions(profileId, chosen);
      setResult(res);
      if (res.created.length) onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "批量保存失败。");
    } finally {
      setBusy(false);
    }
  }

  const chosenCount = drafts ? drafts.filter((_, i) => selected.has(i)).length : 0;

  return (
    <div className="batch-modal-backdrop" role="dialog" aria-label="批量导入岗位" onClick={onClose}>
      <div className="batch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="batch-modal-head">
          <h2 className="app-card-title">批量导入岗位</h2>
          <button type="button" className="toutou-close" onClick={onClose} aria-label="关闭">×</button>
        </div>

        {result ? (
          <div className="batch-result">
            <p className="batch-result-summary">已创建 {result.created.length} 个岗位{result.errors.length ? `，${result.errors.length} 个失败` : ""}。</p>
            {result.errors.length ? (
              <ul className="batch-result-errors">
                {result.errors.map((e, i) => <li key={i}>第 {e.index + 1} 个：{e.error}</li>)}
              </ul>
            ) : null}
            <div className="mission-action-row">
              <button type="button" className="app-btn primary" onClick={onClose}>完成</button>
            </div>
          </div>
        ) : drafts ? (
          <>
            <p className="batch-note">识别出 {drafts.length} 份招聘信息，确认拆分是否正确，取消勾选不想保存的。</p>
            <div className="batch-draft-list">
              {drafts.map((d, i) => (
                <label key={i} className="batch-draft-card">
                  <input type="checkbox" checked={selected.has(i)} onChange={() => toggle(i)} />
                  <div>
                    <strong>{d.title || `未命名岗位 ${i + 1}`}</strong>
                    <div className="batch-draft-tags">
                      {d.company ? <span className="plaza-tag">{d.company}</span> : null}
                      {d.location ? <span className="plaza-tag">{d.location}</span> : null}
                    </div>
                    {d.description ? <p className="batch-draft-excerpt">{d.description.slice(0, 80).replace(/\s+/g, " ")}…</p> : null}
                  </div>
                </label>
              ))}
            </div>
            <div className="mission-action-row">
              <button type="button" className="app-btn primary" disabled={busy || chosenCount === 0} onClick={() => void save()}>
                {busy ? "保存中…" : `保存勾选的 ${chosenCount} 个为岗位`}
              </button>
              <button type="button" className="app-btn" disabled={busy} onClick={() => { setDrafts(null); setResult(null); }}>
                返回修改原文
              </button>
            </div>
          </>
        ) : (
          <>
            <label className="field-label">
              一次粘贴多个岗位描述（JD），用空行分隔
              <textarea
                value={rawText}
                onChange={(e) => setRawText(e.target.value)}
                rows={14}
                placeholder={"粘贴多份 JD，例如：\n\n字节跳动 - 产品经理实习生\n公司：字节跳动\n岗位：产品经理实习生\n地点：北京\n岗位描述：…\n\n百度 - Agent 产品实习生\n公司：百度\n…"}
              />
            </label>
            {error ? <p className="message error" role="alert">{error}</p> : null}
            <div className="mission-action-row">
              <button type="button" className="app-btn primary" disabled={busy} onClick={() => void parse()}>
                {busy ? "识别中…" : "识别岗位"}
              </button>
              <button type="button" className="app-btn" onClick={onClose}>取消</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
