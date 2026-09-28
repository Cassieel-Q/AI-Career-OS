"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

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
    <main className="start-page">
      <header className="workflow-header start-header">
        <Link className="workflow-brand" href="/missions" aria-label="AI Career OS">
          <span className="workflow-brand-mark" aria-hidden="true">A</span>
          <span>AI Career OS</span>
        </Link>
      </header>
      <section className="start-content" aria-labelledby="start-title">
        <p className="eyebrow">简历驱动的岗位准备</p>
        <h1 id="start-title">先上传简历，再按公司优化</h1>
        <p className="summary">上传后会进入「我的岗位准备」。你可以先为百度改一版，再另建小红书或字节的准备，互不影响。</p>
        <form className="upload-panel" onSubmit={(event) => void upload(event)}>
          <label htmlFor="resume">简历 PDF</label>
          <input
            id="resume"
            type="file"
            accept="application/pdf,.pdf"
            disabled={loading}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError("");
            }}
          />
          {file && <p className="file-name">已选择：{file.name}</p>}
          {error && (
            <p className="message error" role="alert">
              {error}
            </p>
          )}
          <button type="submit" disabled={loading || !file}>
            {loading ? "正在解析简历…" : "上传并进入岗位准备"}
          </button>
          {loading && (
            <p className="profile-note" role="status">
              正在提取简历事实，请稍候。
            </p>
          )}
        </form>
        <div className="existing-profile-panel">
          <p className="section-kicker">已有档案？</p>
          <p className="profile-note">从本机已保存的档案中选择。上传「个人简历.pdf」后会显示为「个人简历」，无需粘贴 ID。</p>
          <div className="existing-profile-row">
            <select
              className="text-input"
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
            <button
              type="button"
              className="button-secondary"
              disabled={!selectedProfileId.trim()}
              onClick={() => {
                const id = selectedProfileId.trim();
                window.localStorage.setItem(PROFILE_STORAGE_KEY, id);
                router.push(`/missions?profile_id=${encodeURIComponent(id)}`);
              }}
            >
              进入我的岗位准备
            </button>
            <button
              type="button"
              className="button-secondary"
              disabled={!selectedProfileId.trim() || Boolean(deletingProfileId)}
              onClick={() => void deleteSelectedProfile()}
            >
              {deletingProfileId ? "删除中…" : "删除简历"}
            </button>
          </div>
          {!profiles.length && (
            <p className="profile-note">本机还没有记住的档案。服务器上的档案不会因此消失，可在下方输入档案 ID 恢复，或先上传一份简历 PDF。</p>
          )}
          <div className="existing-profile-recover" style={{ marginTop: "1rem" }}>
            <label className="field-label" htmlFor="recover-profile-id">
              恢复已有档案 / 输入档案 ID
            </label>
            <div className="existing-profile-row">
              <input
                id="recover-profile-id"
                className="text-input"
                value={recoverId}
                disabled={loading || recovering}
                placeholder="粘贴档案 ID"
                onChange={(event) => setRecoverId(event.target.value)}
              />
              <button
                type="button"
                className="button-secondary"
                disabled={loading || recovering || !recoverId.trim()}
                onClick={() => void recoverExistingProfile()}
              >
                {recovering ? "恢复中…" : "恢复已有档案"}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  );
}
