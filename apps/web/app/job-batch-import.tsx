"use client";

import { useState } from "react";
import type { CandidateJob } from "./career-hub.ts";
import {
  confirmCandidateJob,
  importCandidateJob,
  parseCandidateJobs,
  rejectCandidateJob,
  updateCandidateJob,
} from "./career-hub.ts";
import { createDraftProfile } from "./missions.ts";
import { PROFILE_STORAGE_KEY } from "./missions.ts";
import { ImportDropzone, type AcceptedImport } from "./import-dropzone.tsx";

type Props = {
  onClose: () => void;
  onDone: () => void;
};

const RECOGNITION_LABEL: Record<string, string> = {
  MODEL_SPLIT: "模型拆分",
  HEURISTIC_SPLIT: "自动拆分",
  WHOLE_TEXT: "整篇（未拆分）",
  MANUAL: "人工修改",
};

const WARNING_LABEL: Record<string, string> = {
  company_missing: "未识别到公司",
  role_missing: "未识别到岗位",
  location_missing: "未识别到地点",
  company_not_in_source: "公司不在原文中，已清空",
  role_not_in_source: "岗位不在原文中，已清空",
  location_not_in_source: "地点不在原文中，已清空",
};

function warningText(code: string): string {
  return WARNING_LABEL[code] ?? code;
}

export function JobBatchImport({ onClose, onDone }: Props) {
  const [rawText, setRawText] = useState("");
  const [candidates, setCandidates] = useState<CandidateJob[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [importedCount, setImportedCount] = useState(0);
  const [excerptOpen, setExcerptOpen] = useState<Set<string>>(new Set());

  async function handleAccepted(files: AcceptedImport[]) {
    const chunks: string[] = [];
    for (const item of files) {
      if (item.kind === "text") {
        // eslint-disable-next-line no-await-in-loop
        chunks.push(await item.file.text());
      }
    }
    if (!chunks.length) {
      setError("已通过文件校验，但浏览器端无法解析 PDF/DOCX 的二进制文本，请把内容粘贴到下方输入框。");
      return;
    }
    setError("");
    setRawText((prev) => [prev.trim(), ...chunks].filter(Boolean).join("\n\n"));
  }

  async function resolveProfileId(): Promise<string> {
    let profileId = window.localStorage.getItem(PROFILE_STORAGE_KEY)?.trim() || "";
    if (!profileId) {
      const draft = await createDraftProfile();
      profileId = draft.profile_id;
      window.localStorage.setItem(PROFILE_STORAGE_KEY, profileId);
    }
    return profileId;
  }

  async function parse() {
    if (rawText.trim().length < 20) {
      setError("请先粘贴至少一段完整的岗位描述。");
      return;
    }
    setBusy(true);
    setError("");
    setImportedCount(0);
    try {
      const profileId = await resolveProfileId();
      const list = await parseCandidateJobs(profileId, rawText.trim());
      setCandidates(list);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "识别失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  function replaceCandidate(next: CandidateJob) {
    setCandidates((prev) => (prev ? prev.map((c) => (c.id === next.id ? next : c)) : prev));
  }

  async function edit(candidate: CandidateJob, patch: { company?: string; role?: string; location?: string }) {
    try {
      const next = await updateCandidateJob(candidate.id, patch);
      replaceCandidate(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "修改失败。");
    }
  }

  async function confirmOne(candidate: CandidateJob) {
    try {
      replaceCandidate(await confirmCandidateJob(candidate.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "确认失败。");
    }
  }

  async function rejectOne(candidate: CandidateJob) {
    try {
      replaceCandidate(await rejectCandidateJob(candidate.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "拒绝失败。");
    }
  }

  async function importOne(candidate: CandidateJob) {
    setBusy(true);
    setError("");
    try {
      const result = await importCandidateJob(candidate.id);
      setImportedCount((n) => n + (result.reused ? 0 : 1));
      const next = await confirmCandidateJob(candidate.id).catch(() => null);
      setCandidates((prev) =>
        prev
          ? prev.map((c) =>
              c.id === candidate.id
                ? { ...(next ?? c), status: "IMPORTED", imported_mission_id: result.mission_id }
                : c,
            )
          : prev,
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "导入失败。");
    } finally {
      setBusy(false);
    }
  }

  async function importAllConfirmed() {
    if (!candidates) return;
    const confirmed = candidates.filter((c) => c.status === "CONFIRMED");
    if (!confirmed.length) {
      setError("请先确认至少一条候选岗位。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      for (const candidate of confirmed) {
        // 串行导入，避免同一 profile 下的并发竞态
        // eslint-disable-next-line no-await-in-loop
        const result = await importCandidateJob(candidate.id);
        if (!result.reused) setImportedCount((n) => n + 1);
        setCandidates((prev) =>
          prev
            ? prev.map((c) =>
                c.id === candidate.id
                  ? { ...c, status: "IMPORTED", imported_mission_id: result.mission_id }
                  : c,
              )
            : prev,
        );
      }
      onDone();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "批量导入失败。");
    } finally {
      setBusy(false);
    }
  }

  function toggleExcerpt(id: string) {
    setExcerptOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const total = candidates?.length ?? 0;
  const confirmedCount = candidates?.filter((c) => c.status === "CONFIRMED").length ?? 0;
  const importedTotal = candidates?.filter((c) => c.status === "IMPORTED").length ?? 0;

  return (
    <div className="batch-modal-backdrop" role="dialog" aria-label="批量导入岗位" onClick={onClose}>
      <div className="batch-modal" onClick={(e) => e.stopPropagation()}>
        <div className="batch-modal-head">
          <h2 className="app-card-title">批量导入岗位</h2>
          <button type="button" className="toutou-close" onClick={onClose} aria-label="关闭">×</button>
        </div>

        {candidates ? (
          <>
            <p className="batch-note">
              识别出 {total} 份候选岗位草稿，请逐条核对公司/岗位/地点并确认后再导入。候选岗位会保留原文摘录用于回溯。
            </p>
            <div className="batch-draft-list">
              {candidates.map((c, i) => {
                const editable = c.status === "DRAFT" || c.status === "CONFIRMED";
                return (
                  <div key={c.id} className="batch-draft-card editable">
                    <div className="batch-draft-head">
                      <strong>{c.title || `未命名岗位 ${i + 1}`}</strong>
                      <span className={`app-badge ${c.status === "IMPORTED" ? "filled" : c.status === "REJECTED" ? "attention" : "muted"}`}>
                        {c.status === "DRAFT" ? "待确认" : c.status === "CONFIRMED" ? "已确认" : c.status === "IMPORTED" ? "已导入" : "已拒绝"}
                      </span>
                    </div>
                    <div className="batch-draft-tags">
                      <span className="plaza-tag muted">识别来源：{RECOGNITION_LABEL[c.recognition_source] ?? c.recognition_source}</span>
                      {c.location ? <span className="plaza-tag">{c.location}</span> : null}
                      {c.imported_mission_id ? <span className="plaza-tag status">已生成岗位</span> : null}
                    </div>
                    <div className="batch-draft-fields">
                      <label>公司<input type="text" defaultValue={c.company ?? ""} disabled={!editable} onBlur={(e) => void edit(c, { company: e.target.value })} /></label>
                      <label>岗位<input type="text" defaultValue={c.role ?? ""} disabled={!editable} onBlur={(e) => void edit(c, { role: e.target.value })} /></label>
                      <label>地点<input type="text" defaultValue={c.location ?? ""} disabled={!editable} onBlur={(e) => void edit(c, { location: e.target.value })} /></label>
                    </div>
                    {c.warnings.length ? (
                      <ul className="batch-draft-warnings">
                        {c.warnings.map((w) => <li key={w}>⚠ {warningText(w)}</li>)}
                      </ul>
                    ) : null}
                    <button type="button" className="batch-excerpt-toggle" onClick={() => toggleExcerpt(c.id)}>
                      {excerptOpen.has(c.id) ? "收起原文摘录" : "查看原文摘录"}
                    </button>
                    {excerptOpen.has(c.id) ? (
                      <pre className="batch-draft-excerpt">{c.source_excerpt}</pre>
                    ) : null}
                    <div className="mission-action-row">
                      {c.status === "DRAFT" ? (
                        <button type="button" className="app-btn" onClick={() => void confirmOne(c)}>确认</button>
                      ) : null}
                      {c.status !== "IMPORTED" && c.status !== "REJECTED" ? (
                        <button type="button" className="app-btn" onClick={() => void rejectOne(c)}>拒绝</button>
                      ) : null}
                      {c.status === "CONFIRMED" ? (
                        <button type="button" className="app-btn primary" disabled={busy} onClick={() => void importOne(c)}>
                          导入为正式岗位
                        </button>
                      ) : null}
                    </div>
                  </div>
                );
              })}
            </div>
            {error ? <p className="message error" role="alert">{error}</p> : null}
            <div className="mission-action-row">
              <button type="button" className="app-btn primary" disabled={busy || confirmedCount === 0} onClick={() => void importAllConfirmed()}>
                {busy ? "导入中…" : `导入已确认的 ${confirmedCount} 个`}
              </button>
              <button type="button" className="app-btn" disabled={busy} onClick={() => { setCandidates(null); setImportedCount(0); }}>
                返回修改原文
              </button>
              <button type="button" className="app-btn" onClick={onClose}>
                {importedTotal ? "完成" : "取消"}
              </button>
            </div>
            {importedCount ? <p className="batch-result-summary">本次新导入 {importedCount} 个岗位（已存在的岗位会自动复用，不重复创建）。</p> : null}
          </>
        ) : (
          <>
            <ImportDropzone
              purpose="jd"
              multiple
              disabled={busy}
              hint="支持 .txt / .md / .pdf / .docx，单个不超过 10MB；txt/md 会直接读入"
              onAccept={(files) => void handleAccepted(files)}
            />
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
                {busy ? "识别中…" : "生成候选岗位"}
              </button>
              <button type="button" className="app-btn" onClick={onClose}>取消</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
