"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import { archiveMission, listMissions, missionHref, MISSION_API_BASE_URL, PROFILE_STORAGE_KEY, readProfile } from "./missions.ts";
import type { Mission } from "./missions.ts";
import { deleteProfileRequest } from "./profile-flow.ts";
import { deriveTab, isUnknownIdentity, missionIdentityLabel, missionStatusLabel, seniorityLabel } from "./mission-state.ts";
import {
  ensureProfileOption,
  listProfileLabelOptions,
  upsertProfileLabel,
  upsertProfileLabelFromSnapshot,
  removeProfileLabel,
} from "./profile-label.ts";

type ProfileOption = { profileId: string; label: string; displayLabel?: string };

export function MissionsHome() {
  const [profileId, setProfileId] = useState("");
  const [profiles, setProfiles] = useState<ProfileOption[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState("");
  const [error, setError] = useState("");
  const [recoverProfileId, setRecoverProfileId] = useState("");
  const [recovering, setRecovering] = useState(false);
  const [deletingProfileId, setDeletingProfileId] = useState("");

  const newHref = (profileId.trim()
    ? `/missions/new?profile_id=${encodeURIComponent(profileId.trim())}`
    : "/missions/new") as Route;

  const load = useCallback(async (value: string) => {
    const normalized = value.trim();
    if (!normalized) {
      setMissions([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      window.localStorage.setItem(PROFILE_STORAGE_KEY, normalized);
      upsertProfileLabel(normalized, "档案", "fallback");
      setProfiles(ensureProfileOption(normalized, listProfileLabelOptions()));
      setMissions(await listMissions(normalized));
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "读取岗位准备失败。";
      if (/profile not found|档案不存在|HTTP 404/i.test(message)) {
        window.localStorage.removeItem(PROFILE_STORAGE_KEY);
        removeProfileLabel(normalized);
        setProfileId("");
        setProfiles(listProfileLabelOptions());
        setMissions([]);
        setError("本地演示数据库中没有这份简历档案，请重新上传简历。");
      } else if (/failed to fetch|networkerror|网络请求失败/i.test(message)) {
        setError("无法连接后端服务，请确认 API 已启动：http://127.0.0.1:8000。");
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const initial = params.get("profile_id")?.trim() || window.localStorage.getItem(PROFILE_STORAGE_KEY) || "";

    const bootstrap = async () => {
      if (initial) {
        upsertProfileLabel(initial, "档案", "fallback");
        try {
          const snapshot = await readProfile(initial);
          upsertProfileLabelFromSnapshot(initial, snapshot);
        } catch {
          // Keep fallback / prior resume basename.
        }
        setProfiles(ensureProfileOption(initial, listProfileLabelOptions()));
        setProfileId(initial);
        await load(initial);
        return;
      }
      setProfiles(listProfileLabelOptions());
    };

    void bootstrap();
  }, [load]);


  async function onRecoverProfile() {
    const id = recoverProfileId.trim();
    if (!id) {
      setError("请输入档案 ID。");
      return;
    }
    setRecovering(true);
    setError("");
    try {
      const snapshot = await readProfile(id);
      window.localStorage.setItem(PROFILE_STORAGE_KEY, id);
      const label = upsertProfileLabelFromSnapshot(id, snapshot);
      upsertProfileLabel(id, label || "未命名档案", "profile");
      setProfiles(ensureProfileOption(id, listProfileLabelOptions()));
      setProfileId(id);
      setRecoverProfileId("");
      await load(id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "无法恢复该档案，请检查档案 ID。");
    } finally {
      setRecovering(false);
    }
  }

  function onSelectProfile(nextId: string) {
    setProfileId(nextId);
    setError("");
    if (!nextId.trim()) {
      setMissions([]);
      return;
    }
    void load(nextId);
  }

  async function onDeleteProfile(profile: ProfileOption) {
    const id = profile.profileId.trim();
    if (!id || deletingProfileId) return;
    const label = profile.displayLabel || profile.label || "这份简历档案";
    if (!window.confirm(`确定永久删除「${label}」吗？原始简历、岗位准备、优化版本和面试记录都会删除，且无法恢复。`)) return;
    setDeletingProfileId(id);
    setError("");
    try {
      await deleteProfileRequest(id, MISSION_API_BASE_URL);
      removeProfileLabel(id);
      setProfiles((prev) => prev.filter((item) => item.profileId !== id));
      if (profileId === id) {
        window.localStorage.removeItem(PROFILE_STORAGE_KEY);
        setProfileId("");
        setMissions([]);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除简历档案失败，请重试。");
    } finally {
      setDeletingProfileId("");
    }
  }

  async function onDeleteMission(mission: Mission) {
    const label = missionIdentityLabel(mission) || "这份岗位准备";
    const ok = window.confirm(`确定删除「${label}」吗？删除后将从列表中移除。`);
    if (!ok) return;
    setDeletingId(mission.id);
    setError("");
    try {
      await archiveMission(mission.id);
      setMissions((prev) => prev.filter((item) => item.id !== mission.id));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除岗位准备失败。");
    } finally {
      setDeletingId("");
    }
  }

  return (
    <main className="app-page">
      <section className="mission-home-content">
        <header className="app-page-header">
          <div>
            <p className="app-eyebrow">Jobs</p>
            <h1 className="app-page-title">岗位广场</h1>
            <p className="app-page-subtitle">集中管理目标岗位、简历版本与面试准备。</p>
          </div>
        </header>

        <div className="mission-home-actions">
          <Link className="mission-primary-cta link-cta" href={newHref}>
            新建岗位
          </Link>
          <Link className="button-secondary" href={"/interview-records" as Route}>
            面试记录库
          </Link>
          <Link className="button-secondary" href="/workflow/start">
            上传简历
          </Link>
        </div>

        <div className="mission-profile-form">
          <label className="field-label">
            选择已有档案（可选）
            {profiles.length ? (
              <select
                value={profileId}
                disabled={loading}
                onChange={(event) => onSelectProfile(event.target.value)}
                aria-label="选择已有档案"
              >
                <option value="">暂不选择（可直接准备新岗位）</option>
                {profiles.map((profile) => (
                  <option key={profile.profileId} value={profile.profileId}>
                    {profile.displayLabel || profile.label || "未命名档案"}
                  </option>
                ))}
              </select>
            ) : (
              <p className="profile-note">还没有已保存的简历。可上传新简历，或直接添加岗位。</p>
            )}
          </label>
          {profiles.length ? (
            <div className="profile-list-actions">
              <span className="profile-note">删除选中的简历档案</span>
              <button
                type="button"
                className="button-secondary"
                disabled={!profileId || loading || Boolean(deletingProfileId)}
                onClick={() => {
                  const selected = profiles.find((item) => item.profileId === profileId);
                  if (selected) void onDeleteProfile(selected);
                }}
              >
                {deletingProfileId ? "删除中…" : "删除简历"}
              </button>
            </div>
          ) : null}
          <div className="mission-profile-recover">
            <label className="field-label">
              恢复已有档案
              <input
                className="text-input"
                value={recoverProfileId}
                disabled={loading || recovering}
                placeholder="粘贴档案 ID"
                aria-label="输入档案 ID 恢复"
                onChange={(event) => setRecoverProfileId(event.target.value)}
              />
            </label>
            <button
              type="button"
              className="button-secondary"
              disabled={loading || recovering || !recoverProfileId.trim()}
              onClick={() => void onRecoverProfile()}
            >
              {recovering ? "恢复中…" : "恢复已有档案"}
            </button>
          </div>
          {loading ? (
            <p className="profile-note" role="status">
              读取中…
            </p>
          ) : null}
        </div>
        <p className="profile-note" id="mission-profile-hint">已保存的简历可用于多个岗位。</p>

        {error && (
          <p className="message error" role="alert">
            {error}
          </p>
        )}

        <section className="mission-list" aria-label="我的岗位准备">
          {missions.length ? (
            missions.map((mission) => {
              const openTab = deriveTab(mission.workflow_state, {
                resumeSource: mission.resume_source,
                resumeStrategy: mission.resume_strategy,
              });
              const label = missionIdentityLabel(mission);
              const company = isUnknownIdentity(mission.company) ? "" : String(mission.company).trim();
              const role = isUnknownIdentity(mission.role) ? "" : String(mission.role).trim();
              const seniority = seniorityLabel(mission.seniority);
              const workflow = String(mission.workflow_state || "");
              const resumeState = mission.resume_source?.mode ? "已选择" : "待选择";
              const interviewState = ["INTERVIEW_DEBRIEF_READY", "OUTCOME"].includes(workflow)
                ? "已完成"
                : workflow === "INTERVIEW_IN_PROGRESS" ? "进行中" : "待开始";
              const updatedAt = new Date(mission.updated_at);
              return (
                <article className="mission-list-card" key={mission.id}>
                  <Link className="mission-list-card-main" href={missionHref(mission.id, openTab)}>
                    <div>
                      {company ? <p className="section-kicker">{company}</p> : null}
                      <h2>{role || label}</h2>
                      {seniority ? <p>{seniority}</p> : null}
                      <div className="mission-list-meta"><span>简历：{resumeState}</span><span>面试：{interviewState}</span><time dateTime={mission.updated_at}>更新于 {Number.isNaN(updatedAt.getTime()) ? "未知" : updatedAt.toLocaleDateString("zh-CN")}</time></div>
                    </div>
                    <span className="mission-status-badge">{missionStatusLabel(mission.status)}</span>
                  </Link>
                  <button
                    type="button"
                    className="mission-list-delete"
                    aria-label={`删除 ${label}`}
                    title="删除这份岗位准备"
                    disabled={deletingId === mission.id || loading}
                    onClick={() => void onDeleteMission(mission)}
                  >
                    {deletingId === mission.id ? "删除中…" : "删除"}
                  </button>
                </article>
              );
            })
          ) : (
            <div className="mission-empty">
              还没有岗位档案。添加 JD 后即可开始。
            </div>
          )}
        </section>
      </section>
    </main>
  );
}
