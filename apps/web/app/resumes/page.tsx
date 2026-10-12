"use client";

/**
 * 简历中心（合并原「工具 → 上传简历」入口）。
 *
 * 用户反馈：「上传简历后这里没有简历；工具那里的上传简历和这里的简历变成一个；
 * 可以上传简历，也可以直接在这里打开简历工作台；工作台放原始文字供用户自己修改，
 * 简历也要支持拖动 PDF 进去。」
 *
 * 因此本页承担三件事：
 * 1. 简历档案：拖拽 / 点选 PDF 直接上传建档案，也能按档案 ID 恢复、删除档案；
 * 2. 简历工作台：直接编辑简历**原始文字**（保存原文 / 保存并重新提取事实）；
 * 3. 定向简历版本：原有按岗位生成的版本表格（保留）。
 */
import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchResumesOverview, readCurrentProfileId, type ResumesOverviewRead } from "../career-hub.ts";
import { isUnknownIdentity } from "../mission-state.ts";
import { ImportDropzone } from "../import-dropzone.tsx";
import type { AcceptedImport } from "../import-dropzone.tsx";
import { deleteProfileRequest, readApiPayload, type Profile } from "../profile-flow.ts";
import {
  listProfileLabelOptions,
  removeProfileLabel,
  upsertProfileLabelFromFilename,
  upsertProfileLabelFromSnapshot,
} from "../profile-label.ts";
import { PROFILE_STORAGE_KEY, ingestResumeText, readProfile } from "../missions.ts";
import { API_BASE_URL } from "../workflow-state.ts";
import { fetchResumeText, saveResumeText } from "../job-insight.ts";

const FILTERS = [
  { key: "ALL", label: "全部版本" },
  { key: "CONFIRMED", label: "已确认" },
  { key: "DRAFT", label: "草稿" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

const RESUME_SOURCE_LABEL: Record<string, string> = {
  EDITED_TEXT: "你在工作台编辑过的原文",
  PROFILE_FACTS: "由已确认的简历事实自动汇总",
  MISSING: "还没有可编辑的简历原文",
};

export default function ResumesPage() {
  const [profileId, setProfileId] = useState("");
  const [profileLabel, setProfileLabel] = useState("");
  const [overview, setOverview] = useState<ResumesOverviewRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState<FilterKey>("ALL");
  const [query, setQuery] = useState("");

  const [uploading, setUploading] = useState(false);
  const [recoverId, setRecoverId] = useState("");
  const [recovering, setRecovering] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const [resumeText, setResumeText] = useState("");
  const [resumeTextSource, setResumeTextSource] = useState("");
  const [textLoading, setTextLoading] = useState(false);
  const [savingText, setSavingText] = useState(false);
  const [reparsing, setReparsing] = useState(false);
  const studioRef = useRef<HTMLElement | null>(null);

  const refreshLabel = useCallback((id: string) => {
    const option = listProfileLabelOptions().find((item) => item.profileId === id);
    setProfileLabel(option?.displayLabel || option?.label || "");
  }, []);

  const loadOverview = useCallback(async () => {
    const pid = readCurrentProfileId();
    setProfileId(pid);
    if (!pid) {
      setLoading(false);
      setOverview(null);
      return;
    }
    refreshLabel(pid);
    setLoading(true);
    setError("");
    try {
      setOverview(await fetchResumesOverview(pid));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取简历失败。");
    } finally {
      setLoading(false);
    }
  }, [refreshLabel]);

  const loadResumeText = useCallback(async (pid: string) => {
    setTextLoading(true);
    try {
      const payload = await fetchResumeText(pid);
      setResumeText(payload.raw_text);
      setResumeTextSource(payload.source);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取简历原文失败。");
    } finally {
      setTextLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    if (!profileId) {
      setResumeText("");
      setResumeTextSource("");
      return;
    }
    void loadResumeText(profileId);
  }, [profileId, loadResumeText]);

  /** 拖拽 / 点选上传：直接建档案，并记住本机档案 ID。 */
  async function uploadFiles(items: AcceptedImport[]) {
    const first = items[0];
    if (!first || uploading) return;
    setUploading(true);
    setError("");
    setNotice("");
    const body = new FormData();
    body.append("file", first.file);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/resumes`, { method: "POST", body });
      const profile = await readApiPayload<Profile>(response);
      window.localStorage.setItem(PROFILE_STORAGE_KEY, profile.profile_id);
      upsertProfileLabelFromFilename(profile.profile_id, first.file.name);
      refreshLabel(profile.profile_id);
      setProfileId(profile.profile_id);
      setNotice("简历已上传并完成解析，可以直接在下面的简历工作台里修改原始文字。");
      await loadOverview();
      // 上传后自动滚到工作台，避免用户以为「上传了却没有简历」。
      window.setTimeout(() => studioRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "简历上传失败，请重试。");
    } finally {
      setUploading(false);
    }
  }

  async function recoverExistingProfile() {
    const id = recoverId.trim();
    if (!id) {
      setError("请输入档案 ID。");
      return;
    }
    setRecovering(true);
    setError("");
    try {
      const snapshot = await readProfile(id);
      window.localStorage.setItem(PROFILE_STORAGE_KEY, id);
      upsertProfileLabelFromSnapshot(id, snapshot);
      setRecoverId("");
      setNotice("已切换到该档案。");
      setProfileId(id);
      refreshLabel(id);
      await loadOverview();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法恢复该档案，请检查档案 ID。");
    } finally {
      setRecovering(false);
    }
  }

  async function deleteProfile() {
    const id = profileId.trim();
    if (!id || deleting) return;
    const label = profileLabel || "这份简历档案";
    if (!window.confirm(`确定永久删除「${label}」吗？原始简历、岗位准备、优化版本和面试记录都会删除，且无法恢复。`)) return;
    setDeleting(true);
    setError("");
    try {
      await deleteProfileRequest(id, API_BASE_URL);
      removeProfileLabel(id);
      window.localStorage.removeItem(PROFILE_STORAGE_KEY);
      setProfileId("");
      setProfileLabel("");
      setResumeText("");
      setNotice("");
      setOverview(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除简历档案失败，请重试。");
    } finally {
      setDeleting(false);
    }
  }

  async function saveTextOnly() {
    if (!profileId || savingText) return;
    setSavingText(true);
    setError("");
    setNotice("");
    try {
      const payload = await saveResumeText(profileId, resumeText);
      setResumeText(payload.raw_text);
      setResumeTextSource(payload.source);
      setNotice("简历原文已保存。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存简历原文失败。");
    } finally {
      setSavingText(false);
    }
  }

  async function saveAndReparse() {
    if (!profileId || reparsing) return;
    if (resumeText.trim().length < 40) {
      setError("简历太短，至少 40 个字才能重新提取事实。");
      return;
    }
    setReparsing(true);
    setError("");
    setNotice("");
    try {
      // 先落盘原文，保证「重新解析」用的就是用户刚改过的文字。
      await saveResumeText(profileId, resumeText);
      await ingestResumeText(profileId, resumeText);
      setResumeTextSource("EDITED_TEXT");
      setNotice("已按新原文重新提取简历事实。");
      await loadOverview();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重新提取失败，请重试。");
    } finally {
      setReparsing(false);
    }
  }

  const filtered = useMemo(() => {
    const keyword = query.trim().toLowerCase();
    return (overview?.resumes ?? []).filter((resume) => {
      if (filter === "CONFIRMED" && !resume.confirmed) return false;
      if (filter === "DRAFT" && resume.confirmed) return false;
      if (!keyword) return true;
      return [resume.role, resume.company].join(" ").toLowerCase().includes(keyword);
    });
  }, [overview, filter, query]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Resumes</p>
          <h1 className="app-page-title">简历中心</h1>
          <p className="app-page-subtitle">上传或修改简历原文，再针对每个岗位生成定向版本——一份简历，多处复用。</p>
        </div>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}
      {notice ? <p className="message success" role="status">{notice}</p> : null}

      <section className="app-card resume-archive">
        <div className="start-card-head">
          <div>
            <h2>简历档案</h2>
            <p>{profileId ? "当前使用的档案；可直接换文件、改原文或删除。" : "拖一份 PDF 进来，30 秒后就能开始准备岗位。"}</p>
          </div>
        </div>

        {profileId ? (
          <p className="resume-archive-current">
            <span className="cell-tag strong">本机当前档案</span>
            <span>{profileLabel || "未命名档案"}</span>
          </p>
        ) : null}

        <ImportDropzone
          purpose="resume-pdf"
          disabled={uploading}
          onAccept={(items) => void uploadFiles(items)}
          hint="拖拽 PDF 到此处，或点击选择；单个不超过 10MB"
        />
        {uploading ? <p className="start-status" role="status">正在解析简历，请稍候…</p> : null}

        <div className="start-row resume-archive-actions">
          <Link className="app-btn" href="/missions">进入岗位准备</Link>
          <button
            type="button"
            className="app-btn danger"
            disabled={!profileId || deleting}
            onClick={() => void deleteProfile()}
          >
            {deleting ? "删除中…" : "删除当前档案"}
          </button>
        </div>

        <details className="start-recover">
          <summary>换一个档案 / 用档案 ID 恢复</summary>
          <label htmlFor="recover-profile-id">档案 ID</label>
          <div className="start-row">
            <input
              id="recover-profile-id"
              className="start-select"
              value={recoverId}
              disabled={recovering || uploading}
              placeholder="粘贴档案 ID"
              onChange={(event) => setRecoverId(event.target.value)}
            />
            <button
              type="button"
              className="app-btn"
              disabled={recovering || !recoverId.trim()}
              onClick={() => void recoverExistingProfile()}
            >
              {recovering ? "恢复中…" : "恢复并切换"}
            </button>
          </div>
        </details>
      </section>

      <section className="app-card resume-studio" id="resume-studio" ref={studioRef}>
        <div className="start-card-head">
          <div>
            <h2>简历工作台</h2>
            <p>这里放的是简历<strong>原始文字</strong>，可以直接改；改完可只保存，也可让系统按新文字重新提取事实。</p>
          </div>
        </div>

        {!profileId ? (
          <p className="app-empty">还没有简历档案，先在上面上传一份 PDF。</p>
        ) : (
          <>
            <p className="start-note">
              内容来源：{RESUME_SOURCE_LABEL[resumeTextSource] ?? "读取中…"}
            </p>
            <textarea
              className="resume-studio-text"
              value={textLoading ? "" : resumeText}
              disabled={textLoading || savingText || reparsing}
              placeholder={textLoading ? "正在读取简历原文…" : "在这里粘贴或修改简历原文"}
              spellCheck={false}
              onChange={(event) => setResumeText(event.target.value)}
            />
            <div className="start-row resume-archive-actions">
              <button
                type="button"
                className="app-btn primary"
                disabled={textLoading || savingText || reparsing}
                onClick={() => void saveTextOnly()}
              >
                {savingText ? "保存中…" : "保存原文"}
              </button>
              <button
                type="button"
                className="app-btn"
                disabled={textLoading || savingText || reparsing}
                onClick={() => void saveAndReparse()}
              >
                {reparsing ? "重新提取中…" : "保存并重新提取事实"}
              </button>
              <span className="start-note">重新提取会把新文字解析成技能 / 经历等事实，用于后续岗位匹配与简历生成。</span>
            </div>
          </>
        )}
      </section>

      <section className="app-card">
        <div className="start-card-head">
          <div>
            <h2>定向简历版本</h2>
            <p>按岗位生成的版本集中管理，进入工作台可继续精修。</p>
          </div>
        </div>

        <section className="app-stat-grid" aria-label="简历概览">
          <div className="app-stat-card"><div className="app-stat-value">{overview?.total ?? 0}</div><div className="app-stat-label">简历版本</div></div>
          <div className="app-stat-card"><div className="app-stat-value">{overview?.resumes.filter((r) => r.confirmed).length ?? 0}</div><div className="app-stat-label">已确认</div></div>
        </section>

        {loading ? (
          <div className="app-empty">读取中…</div>
        ) : !profileId ? (
          <div className="app-empty">还没有简历档案。上传一份 PDF 后，岗位版本会出现在这里。</div>
        ) : !overview?.resumes.length ? (
          <div className="app-empty">还没有简历版本。进入某个岗位完成简历策略后，版本会出现在这里。</div>
        ) : (
          <>
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
                  placeholder="搜索岗位 / 公司"
                  aria-label="搜索岗位或公司"
                />
              </label>
              <select
                className="table-select"
                value={filter}
                onChange={(event) => setFilter(event.target.value as FilterKey)}
                aria-label="按确认状态筛选"
              >
                {FILTERS.map((f) => (
                  <option key={f.key} value={f.key}>{f.label}</option>
                ))}
              </select>
            </div>

            {filtered.length ? (
              <div className="data-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>岗位</th>
                      <th>公司</th>
                      <th>版本</th>
                      <th>要点数</th>
                      <th>更新时间</th>
                      <th>状态</th>
                      <th style={{ textAlign: "right" }}>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((resume) => (
                      <tr key={resume.resume_id}>
                        <td>
                          <div className="cell-title">
                            <Link href={`/missions/${encodeURIComponent(resume.mission_id)}/resume/studio` as Route}>
                              {isUnknownIdentity(resume.role) ? "未命名岗位" : resume.role}
                            </Link>
                          </div>
                        </td>
                        <td>{isUnknownIdentity(resume.company) ? <span className="cell-muted">—</span> : resume.company}</td>
                        <td>v{resume.version}</td>
                        <td>{resume.bullet_count} 条</td>
                        <td>
                          <span className="cell-muted">
                            {resume.updated_at ? new Date(resume.updated_at).toLocaleDateString("zh-CN") : "—"}
                          </span>
                        </td>
                        <td>
                          <span className={`app-badge ${resume.confirmed ? "filled" : "muted"}`}>
                            {resume.confirmed ? "已确认" : "草稿"}
                          </span>
                        </td>
                        <td>
                          <div className="cell-actions">
                            <Link
                              className="app-btn"
                              href={`/missions/${encodeURIComponent(resume.mission_id)}/resume/studio` as Route}
                            >
                              打开工作台
                            </Link>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="app-empty">没有符合当前筛选条件的简历版本。</div>
            )}
          </>
        )}
      </section>
    </main>
  );
}
