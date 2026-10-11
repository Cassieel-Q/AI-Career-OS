"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";

import { deleteProfileRequest, readApiPayload } from "./profile-flow.ts";
import type { Profile } from "./profile-flow.ts";
import { API_BASE_URL } from "./workflow-state.ts";
import { PROFILE_STORAGE_KEY } from "./missions.ts";
import {
  ensureProfileOption,
  listProfileLabelOptions,
  upsertProfileLabelFromFilename,
  upsertProfileLabelFromSnapshot,
  removeProfileLabel,
} from "./profile-label.ts";
import { readProfile } from "./missions.ts";

type ProfileOption = { profileId: string; label: string; displayLabel?: string };

function UploadIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 15V4" />
      <path d="m7.5 8 4.5-4.5L16.5 8" />
      <path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />
    </svg>
  );
}

function ArchiveIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="4" y="4" width="16" height="4.5" rx="1.2" />
      <path d="M6 8.5V19a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V8.5" />
      <path d="M10 12.5h4" />
    </svg>
  );
}

export function ResumeUpload() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [profiles, setProfiles] = useState<ProfileOption[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [recoverId, setRecoverId] = useState("");
  const [recovering, setRecovering] = useState(false);
  const [deletingProfileId, setDeletingProfileId] = useState("");

  useEffect(() => {
    const current = window.localStorage.getItem(PROFILE_STORAGE_KEY) || "";
    setProfiles(ensureProfileOption(current, listProfileLabelOptions()));
    if (current) setSelectedProfileId(current);
  }, []);


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
      setProfiles(ensureProfileOption(id, listProfileLabelOptions()));
      setSelectedProfileId(id);
      router.push(`/missions?profile_id=${encodeURIComponent(id)}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法恢复该档案，请检查档案 ID。");
    } finally {
      setRecovering(false);
    }
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || loading) {
      if (!file) setError("请先选择 PDF 简历。");
      return;
    }

    setLoading(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/resumes`, { method: "POST", body });
      const profile = await readApiPayload<Profile>(response);
      window.localStorage.setItem(PROFILE_STORAGE_KEY, profile.profile_id);
      upsertProfileLabelFromFilename(profile.profile_id, file.name);
      router.replace(`/missions?profile_id=${encodeURIComponent(profile.profile_id)}`);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "简历上传失败，请重试。");
    } finally {
      setLoading(false);
    }
  }

  async function deleteSelectedProfile() {
    const id = selectedProfileId.trim();
    if (!id || deletingProfileId) return;
    const selected = profiles.find((profile) => profile.profileId === id);
    const label = selected?.displayLabel || selected?.label || "这份简历档案";
    if (!window.confirm(`确定永久删除「${label}」吗？原始简历、岗位准备、优化版本和面试记录都会删除，且无法恢复。`)) return;
    setDeletingProfileId(id);
    setError("");
    try {
      await deleteProfileRequest(id, API_BASE_URL);
      removeProfileLabel(id);
      setProfiles((prev) => prev.filter((profile) => profile.profileId !== id));
      window.localStorage.removeItem(PROFILE_STORAGE_KEY);
      setSelectedProfileId("");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除简历档案失败，请重试。");
    } finally {
      setDeletingProfileId("");
    }
  }

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">简历档案</p>
          <h1 className="app-page-title">上传简历</h1>
          <p className="app-page-subtitle">一份简历可用于多个岗位——先核对提取出的事实，再针对不同公司分别优化。</p>
        </div>
      </header>

      <div className="start-grid">
        <section className="app-card">
          <div className="start-card-head">
            <span className="start-card-icon" aria-hidden="true"><UploadIcon /></span>
            <div>
              <h2>上传新简历</h2>
              <p>支持 PDF，上传后自动提取事实并进入核对</p>
            </div>
          </div>
          <form className="start-form" onSubmit={(event) => void upload(event)}>
            <input
              id="resume"
              type="file"
              accept="application/pdf,.pdf"
              disabled={loading}
              hidden
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null);
                setError("");
              }}
            />
            <label className="start-picker" htmlFor="resume">
              <span className="start-picker-badge" aria-hidden="true">PDF</span>
              <span className="start-picker-text">
                <strong>{file ? file.name : "选择 PDF 简历"}</strong>
                <small>{file ? "点击更换文件" : "从本机选择文件"}</small>
              </span>
              <span className="app-btn" aria-hidden="true">浏览文件</span>
            </label>
            {error && <p className="start-error" role="alert">{error}</p>}
            <button type="submit" className="app-btn primary block" disabled={loading || !file}>
              {loading ? "正在解析简历…" : "上传并进入岗位准备"}
            </button>
            {loading && <p className="start-status" role="status">正在提取简历事实，请稍候。</p>}
          </form>
        </section>

        <section className="app-card">
          <div className="start-card-head">
            <span className="start-card-icon" aria-hidden="true"><ArchiveIcon /></span>
            <div>
              <h2>继续已有档案</h2>
              <p>从本机记住的档案继续准备</p>
            </div>
          </div>
          <div className="start-stack">
            <select
              className="start-select"
              aria-label="选择已有档案"
              value={selectedProfileId}
              onChange={(event) => setSelectedProfileId(event.target.value)}
            >
              <option value="">请选择档案</option>
              {profiles.map((profile) => (
                <option key={profile.profileId} value={profile.profileId}>
                  {profile.displayLabel || profile.label || "未命名档案"}
                </option>
              ))}
            </select>
            <div className="start-row">
              <button
                type="button"
                className="app-btn primary"
                disabled={!selectedProfileId.trim()}
                onClick={() => {
                  const id = selectedProfileId.trim();
                  window.localStorage.setItem(PROFILE_STORAGE_KEY, id);
                  router.push(`/missions?profile_id=${encodeURIComponent(id)}`);
                }}
              >
                进入岗位准备
              </button>
              <button
                type="button"
                className="app-btn danger"
                disabled={!selectedProfileId.trim() || Boolean(deletingProfileId)}
                onClick={() => void deleteSelectedProfile()}
              >
                {deletingProfileId ? "删除中…" : "删除档案"}
              </button>
            </div>
            {!profiles.length && (
              <p className="start-note">本机还没有记住的档案。服务器上的档案不会因此消失，可在下方输入档案 ID 恢复，或先上传一份简历 PDF。</p>
            )}
            <details className="start-recover">
              <summary>用档案 ID 恢复</summary>
              <label htmlFor="recover-profile-id">档案 ID</label>
              <div className="start-row">
                <input
                  id="recover-profile-id"
                  className="start-select"
                  value={recoverId}
                  disabled={loading || recovering}
                  placeholder="粘贴档案 ID"
                  onChange={(event) => setRecoverId(event.target.value)}
                />
                <button
                  type="button"
                  className="app-btn"
                  disabled={loading || recovering || !recoverId.trim()}
                  onClick={() => void recoverExistingProfile()}
                >
                  {recovering ? "恢复中…" : "恢复已有档案"}
                </button>
              </div>
            </details>
          </div>
        </section>
      </div>
    </main>
  );
}
