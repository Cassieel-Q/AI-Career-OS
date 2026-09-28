"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";

import {
  confirmProfileRequest,
  normalizeProfile,
  readApiPayload,
  saveProfileRequest,
} from "./profile-flow.ts";
import type { Experience, Profile } from "./profile-flow.ts";
import { MISSION_API_BASE_URL } from "./missions.ts";

type MissionProfileConfirmCardProps = {
  boundProfileId: string;
  apiUrl?: string;
  busy?: boolean;
  onConfirmed: () => Promise<void> | void;
  /** Notify parent whether this bound profile still blocks proof / later resume steps. */
  onNeedsConfirmChange?: (needsConfirm: boolean) => void;
};

async function fetchBoundProfile(profileId: string, apiUrl: string): Promise<Profile> {
  const response = await fetch(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}`);
  const raw = await readApiPayload<Profile & { id?: string; profile_id?: string }>(response);
  return normalizeProfile({
    ...raw,
    profile_id: String(raw.profile_id ?? raw.id ?? profileId),
  });
}

/**
 * In-mission confirm gate for mission_local bound DRAFT profiles.
 * Stays on the mission page (does not redirect to abandoned /workflow/.../profile).
 */
export function MissionProfileConfirmCard({
  boundProfileId,
  apiUrl = MISSION_API_BASE_URL,
  busy = false,
  onConfirmed,
  onNeedsConfirmChange,
}: MissionProfileConfirmCardProps) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState<"draft" | "confirm" | null>(null);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      setProfile(await fetchBoundProfile(boundProfileId, apiUrl));
    } catch (caught) {
      setProfile(null);
      setLoadError(caught instanceof Error ? caught.message : "无法加载岗位简历档案");
    } finally {
      setLoading(false);
    }
  }, [apiUrl, boundProfileId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!onNeedsConfirmChange) return;
    if (loading) return;
    if (loadError) {
      onNeedsConfirmChange(true);
      return;
    }
    onNeedsConfirmChange(Boolean(profile && profile.status !== "CONFIRMED"));
  }, [loading, loadError, onNeedsConfirmChange, profile]);

  if (loading && !profile) {
    return (
      <section className="mission-card" role="status">
        <p className="mission-pipeline-note">正在检查这份岗位简历是否已确认…</p>
      </section>
    );
  }

  if (loadError) {
    return (
      <section className="mission-card" role="alert">
        <p className="message error">{loadError}</p>
        <button type="button" className="button-secondary" disabled={busy} onClick={() => void reload()}>
          重试
        </button>
      </section>
    );
  }

  if (!profile || profile.status === "CONFIRMED") {
    return null;
  }

  // Compare as string so TS does not narrow ProfileStatus to never after the CONFIRMED early-return.
  const profileStatus: string = profile.status;

  async function saveDraft() {
    if (!profile || saving) return;
    setSaving("draft");
    setError("");
    try {
      const saved = normalizeProfile(await saveProfileRequest(profile, apiUrl));
      setProfile(saved);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存草稿失败");
    } finally {
      setSaving(null);
    }
  }

  async function confirmProfile() {
    if (!profile || saving) return;
    setSaving("confirm");
    setError("");
    try {
      const confirmed = normalizeProfile(await confirmProfileRequest(profile, false, apiUrl));
      setProfile(confirmed);
      setOpen(false);
      await onConfirmed();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "确认 Profile 失败");
    } finally {
      setSaving(null);
    }
  }

  const mutationBusy = busy || saving !== null;

  return (
    <section className="mission-card" style={{ borderColor: "var(--warning, #c47b1a)" }}>
      <p className="section-kicker">岗位简历确认</p>
      <h3>请先确认这份岗位简历中的事实</h3>
      <p className="summary">
        这份上传简历只绑定当前岗位。确认后，系统才会使用其中的经历生成证明和面试追问。
      </p>
      <div className="mission-action-row" style={{ marginTop: "0.75rem" }}>
        <button
          type="button"
          className="button-primary"
          disabled={mutationBusy}
          onClick={() => {
            setOpen(true);
            setError("");
          }}
        >
          查看并确认 Profile
        </button>
      </div>

      {open && (
        <div
          className="mission-card"
          style={{ marginTop: "1rem", background: "var(--surface-muted, #f7f5f1)" }}
          role="dialog"
          aria-label="确认岗位简历 Profile"
        >
          <div className="section-heading">
            <div>
              <p className="section-kicker">仅本岗位 · 状态 {profile.status}</p>
              <h3>核对教育、技能与经历</h3>
              <p className="summary">请确认事实与简历证据一致。确认不会改写 Master 档案。</p>
            </div>
            <button type="button" className="text-button" disabled={mutationBusy} onClick={() => setOpen(false)}>
              收起
            </button>
          </div>

          <div className="mission-grid mission-grid-2" style={{ marginTop: "0.75rem" }}>
            {([
              ["姓名", "full_name"],
              ["电话", "phone"],
              ["邮箱", "email"],
              ["城市", "city"],
            ] as const).map(([label, key]) => (
              <label className="field-label" key={key}>
                {label}
                <input
                  value={String(profile[key] ?? "")}
                  onChange={(event) => setProfile({ ...profile, [key]: event.target.value })}
                  disabled={mutationBusy}
                />
              </label>
            ))}
          </div>

          <ProfileFactBlock title="教育" empty="暂无教育经历" count={profile.education.length}>
            {profile.education.map((item, index) => (
              <article className="profile-item" key={item.id ?? `edu-${index}`}>
                <strong>{item.institution || "（未填学校）"}</strong>
                <span>
                  {[item.degree, item.field_of_study, item.dates].filter(Boolean).join(" · ") || "—"}
                </span>
                <EvidenceText value={item.evidence_text} />
              </article>
            ))}
          </ProfileFactBlock>

          <ProfileFactBlock title="技能" empty="暂无技能" count={profile.skills.length}>
            {profile.skills.map((item, index) => (
              <article className="profile-item" key={item.id ?? `skill-${index}`}>
                <strong>{item.name || "（未填技能）"}</strong>
                <span>{item.proficiency || "未评估"}</span>
                <EvidenceText value={item.evidence_text} />
              </article>
            ))}
          </ProfileFactBlock>

          <ProfileFactBlock title="经历（工作 / 项目 / 校园）" empty="暂无经历" count={profile.experiences.length}>
            {profile.experiences.map((item, index) => (
              <ExperienceRow key={item.id ?? `exp-${index}`} item={item} />
            ))}
          </ProfileFactBlock>

          {error && (
            <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }} role="alert">
              <p className="message error" style={{ flex: 1 }}>
                确认失败：{error}
              </p>
              <button
                type="button"
                className="button-secondary"
                disabled={mutationBusy}
                onClick={() => void confirmProfile()}
              >
                重试确认
              </button>
            </div>
          )}

          <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
            <button
              type="button"
              className="button-secondary"
              disabled={mutationBusy || profileStatus === "CONFIRMED"}
              onClick={() => void saveDraft()}
            >
              {saving === "draft" ? "保存中…" : "保存草稿"}
            </button>
            <button
              type="button"
              className="button-primary"
              disabled={mutationBusy || profileStatus === "CONFIRMED"}
              onClick={() => void confirmProfile()}
            >
              {saving === "confirm" ? "确认中…" : "确认 Profile"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function ProfileFactBlock({
  title,
  empty,
  count,
  children,
}: {
  title: string;
  empty: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section className="profile-section" style={{ marginTop: "0.75rem" }}>
      <h4>{title}</h4>
      {count > 0 ? children : <p className="empty">{empty}</p>}
    </section>
  );
}

function ExperienceRow({ item }: { item: Experience }) {
  return (
    <article className="profile-item">
      <strong>{item.title || "（未填职位）"}</strong>
      <span>
        {[item.organization, item.dates, item.experience_type].filter(Boolean).join(" · ") || "—"}
      </span>
      {item.description ? <p className="summary">{item.description}</p> : null}
      <EvidenceText value={item.evidence_text} />
    </article>
  );
}

function EvidenceText({ value }: { value: string | null }) {
  return value ? (
    <p className="evidence">
      <span>简历证据</span>
      {value}
    </p>
  ) : (
    <p className="evidence user-provided">
      <span>来源</span>
      用户补充 / 无原文摘录
    </p>
  );
}
