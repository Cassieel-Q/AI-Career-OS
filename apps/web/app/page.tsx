"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import {
  confirmProfileRequest,
  createEmptyEducation,
  getProfileIdFromSearch,
  normalizeProfile,
  profileHref,
  readApiPayload,
  saveProfileRequest,
  validateProfileForSave,
} from "./profile-flow";
import type { Education, Experience, Certification, ExperienceType, Profile, ProfileItem, Proficiency, Skill } from "./profile-flow";
import {
  CAREER_PREFERENCE_OPTIONS,
  careerPreferencesDraftFromProfile,
  isCareerPreferencesDraftValid,
  profileCanEditCareerPreferences,
  saveCareerPreferencesRequest,
  toggleCareerPreference,
} from "./career-preferences";
import type { CareerPreferencePriority, CareerPreferencesDraft } from "./career-preferences";
import {
  ROLE_EXPLORATION_DISCLAIMER,
  ROLE_EXPLORATION_LEVEL_LABELS,
  createRoleExplorationRequest,
  getRoleExplorationRequest,
  profileCanExploreRoles,
  roleExplorationViewData,
} from "./role-exploration";
import type { RoleExplorationRead } from "./role-exploration";

type EditableSection = "education" | "skills" | "experiences" | "certifications";

const proficiencyOptions: Array<{ value: Proficiency; label: string }> = [
  { value: "AWARE", label: "AWARE" },
  { value: "BASIC", label: "BASIC" },
  { value: "PROJECT_READY", label: "PROJECT_READY" },
  { value: "PROFICIENT", label: "PROFICIENT" },
];
const experienceTypeOptions: Array<{ value: ExperienceType; label: string }> = [
  { value: "WORK", label: "Work" },
  { value: "INTERNSHIP", label: "Internship" },
  { value: "CAMPUS", label: "Campus" },
  { value: "PROJECT", label: "Project" },
  { value: "OTHER", label: "Other" },
];

const apiUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [saving, setSaving] = useState<"save" | "confirm" | null>(null);
  const [dirty, setDirty] = useState(false);
  const [preferenceDraft, setPreferenceDraft] = useState<CareerPreferencesDraft>({
    priority_order: [],
    weekly_hours: "",
  });
  const [savingPreferences, setSavingPreferences] = useState(false);
  const [roleExploration, setRoleExploration] = useState<RoleExplorationRead | null>(null);
  const [loadingExploration, setLoadingExploration] = useState(false);
  const [creatingExploration, setCreatingExploration] = useState(false);
  const explorationHydratedProfileId = useRef<string | null>(null);

  useEffect(() => {
    const profileId = getProfileIdFromSearch(window.location.search);
    if (!profileId) return;
    let active = true;
    async function hydrateProfile() {
      setLoadingProfile(true);
      setError("");
      try {
        const response = await fetch(`${apiUrl}/api/v1/profiles/${profileId}`);
        const payload = await readApiPayload<Profile>(response);
        if (active) {
          const normalized = normalizeProfile(payload);
          setProfile(normalized);
          setPreferenceDraft(careerPreferencesDraftFromProfile(normalized));
          setDirty(false);
        }
      } catch (loadError) {
        if (active) setError(loadError instanceof Error ? loadError.message : "Profile could not be loaded.");
      } finally {
        if (active) setLoadingProfile(false);
      }
    }
    void hydrateProfile();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!profile || !profileCanExploreRoles(profile)) {
      setRoleExploration(null);
      return;
    }
    if (explorationHydratedProfileId.current === profile.profile_id) return;
    explorationHydratedProfileId.current = profile.profile_id;
    let active = true;
    setLoadingExploration(true);
    void getRoleExplorationRequest(profile.profile_id, apiUrl)
      .then((snapshot) => { if (active) setRoleExploration(snapshot); })
      .catch(() => { /* 404/not-generated and transient errors keep the page usable. */ })
      .finally(() => { if (active) setLoadingExploration(false); });
    return () => { active = false; };
  }, [profile]);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setProfile(null);
    setPreferenceDraft({ priority_order: [], weekly_hours: "" });
    setDirty(false);
    setError("");
    const url = new URL(window.location.href);
    url.searchParams.delete("profile_id");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError("Choose a PDF resume first.");
      return;
    }
    setLoading(true);
    setError("");
    setProfile(null);
    setPreferenceDraft({ priority_order: [], weekly_hours: "" });
    setDirty(false);
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`${apiUrl}/api/v1/resumes`, {
        method: "POST",
        body,
      });
      const payload = await readApiPayload<Profile>(response);
      const normalized = normalizeProfile(payload);
      setProfile(normalized);
      setPreferenceDraft(careerPreferencesDraftFromProfile(normalized));
      setDirty(false);
      window.history.replaceState(null, "", profileHref(window.location.href, payload.profile_id));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Resume upload failed.");
    } finally {
      setLoading(false);
    }
  }

  function updateItem(section: EditableSection, index: number, field: string, value: string | null) {
    if (!profile || profile.status === "CONFIRMED") return;
    setDirty(true);
    setProfile((current) => {
      if (!current || current.status === "CONFIRMED") return current;
      const items = current[section].map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      );
      return { ...current, [section]: items } as Profile;
    });
  }

  function addItem(section: EditableSection) {
    if (!profile || profile.status === "CONFIRMED") return;
    setDirty(true);
    setProfile((current) => {
      if (!current || current.status === "CONFIRMED") return current;
      const item = newItem(section);
      return { ...current, [section]: [...current[section], item] } as Profile;
    });
  }

  function updateEducationCourses(index: number, value: string) {
    if (!profile || profile.status === "CONFIRMED") return;
    setDirty(true);
    const relevant_courses = value
      .split(/[,，、;；]/)
      .map((course) => course.trim())
      .filter(Boolean);
    setProfile((current) => {
      if (!current || current.status === "CONFIRMED") return current;
      return {
        ...current,
        education: current.education.map((item, itemIndex) =>
          itemIndex === index ? { ...item, relevant_courses } : item,
        ),
      };
    });
  }

  function deleteItem(section: EditableSection, index: number) {
    if (!profile || profile.status === "CONFIRMED") return;
    setDirty(true);
    setProfile((current) => {
      if (!current || current.status === "CONFIRMED") return current;
      return {
        ...current,
        [section]: current[section].filter((_, itemIndex) => itemIndex !== index),
      } as Profile;
    });
  }

  async function saveDraft() {
    const currentProfile = profile;
    if (!currentProfile || currentProfile.status === "CONFIRMED") return;
    const validationError = validateProfileForSave(currentProfile);
    if (validationError) {
      setError(validationError);
      return;
    }
    setSaving("save");
    setError("");
    try {
      const payload = await saveProfileRequest(currentProfile, apiUrl);
      const normalized = normalizeProfile(payload);
      setProfile(normalized);
      setPreferenceDraft(careerPreferencesDraftFromProfile(normalized));
      setDirty(false);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Profile could not be saved.");
    } finally {
      setSaving(null);
    }
  }

  async function confirmProfile() {
    const currentProfile = profile;
    if (!currentProfile || currentProfile.status === "CONFIRMED") return;
    const validationError = validateProfileForSave(currentProfile);
    if (validationError) {
      setError(validationError);
      return;
    }
    setSaving("confirm");
    setError("");
    try {
      const payload = await confirmProfileRequest(currentProfile, dirty, apiUrl);
      const normalized = normalizeProfile(payload);
      setProfile(normalized);
      setPreferenceDraft(careerPreferencesDraftFromProfile(normalized));
      setDirty(false);
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "Profile could not be confirmed.");
    } finally {
      setSaving(null);
    }
  }

  function selectPreference(value: CareerPreferencePriority) {
    if (!profileCanEditCareerPreferences(profile) || savingPreferences) return;
    setRoleExploration(null);
    setPreferenceDraft((current) => ({
      ...current,
      priority_order: toggleCareerPreference(current.priority_order, value),
    }));
  }

  async function savePreferences() {
    const currentProfile = profile;
    if (!currentProfile || !profileCanEditCareerPreferences(currentProfile)) return;
    if (!isCareerPreferencesDraftValid(preferenceDraft.priority_order, preferenceDraft.weekly_hours)) return;
    setSavingPreferences(true);
    setError("");
    setRoleExploration(null);
    try {
      const saved = await saveCareerPreferencesRequest(currentProfile.profile_id, preferenceDraft, apiUrl);
      setPreferenceDraft(careerPreferencesDraftFromProfile({ ...currentProfile, preferences: saved }));
      setProfile((current) => current ? { ...current, preferences: saved } : current);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Career preferences could not be saved.");
    } finally {
      setSavingPreferences(false);
    }
  }

  async function exploreRoles() {
    const currentProfile = profile;
    if (!currentProfile || !explorationReady || creatingExploration) return;
    setCreatingExploration(true);
    setError("");
    try {
      setRoleExploration(await createRoleExplorationRequest(currentProfile.profile_id, apiUrl));
    } catch (explorationError) {
      setError(explorationError instanceof Error ? explorationError.message : "Role exploration could not be generated.");
    } finally {
      setCreatingExploration(false);
    }
  }

  const profileLocked = profile?.status === "CONFIRMED";
  const mutationBusy = saving !== null || savingPreferences;
  const explorationReady = Boolean(
    profileCanExploreRoles(profile) &&
      profile?.preferences &&
      profile.preferences.priority_order.length === preferenceDraft.priority_order.length &&
      profile.preferences.priority_order.every((value, index) => value === preferenceDraft.priority_order[index]) &&
      String(profile.preferences.weekly_hours) === preferenceDraft.weekly_hours,
  );

  return (
    <main className="shell">
      <p className="eyebrow">AI Career OS / Resume intake</p>
      <h1>Build a profile you can stand behind.</h1>
      <p className="summary">
        Start with a text-based PDF. Review the extracted facts, add what is missing, and confirm only when it is yours.
      </p>
      <form className="upload-panel" onSubmit={upload}>
        <label htmlFor="resume">Resume PDF</label>
        <input id="resume" type="file" accept="application/pdf,.pdf" onChange={chooseFile} />
        <button type="submit" disabled={loading || loadingProfile || mutationBusy}>
          {loadingProfile ? "Loading profile..." : loading ? "Extracting..." : "Upload resume"}
        </button>
        {file && <p className="file-name">Selected: {file.name}</p>}
      </form>
      {error && (
        <p className="message error" role="alert">
          {error}
        </p>
      )}
      {profile && (
        <section className="profile" aria-label="User Profile">
          <div className="profile-heading">
            <div>
              <p className="section-kicker">Source of truth</p>
              <h2>User Profile</h2>
            </div>
            <span className={`profile-status ${profile.status.toLowerCase()}`}>{profile.status}</span>
          </div>
          <p className="profile-note">
            {profileLocked
              ? "This profile is confirmed and ready for future career planning."
              : "AI facts keep their resume evidence. Add or correct anything before you confirm."}
          </p>
          <ProfileSection<Education>
            title="Education"
            section="education"
            items={profile.education}
            locked={profileLocked || mutationBusy}
            onAdd={addItem}
            onDelete={deleteItem}
            render={(item, index) => (
              <>
                <div className="field-grid">
                  <TextField label="School" value={item.institution} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("education", index, "institution", value)} />
                  <TextField label="Degree" value={item.degree} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("education", index, "degree", value)} />
                  <TextField label="Major" value={item.field_of_study} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("education", index, "field_of_study", value)} />
                  <TextField label="Dates" value={item.dates} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("education", index, "dates", value)} />
                  <TextField label="Relevant courses" value={(item.relevant_courses ?? []).join(", ")} disabled={profileLocked || mutationBusy} onChange={(value) => updateEducationCourses(index, value ?? "")} />
                </div>
                <Evidence item={item} />
              </>
            )}
          />
          <ProfileSection<Skill>
            title="Skills"
            section="skills"
            items={profile.skills}
            locked={profileLocked || mutationBusy}
            onAdd={addItem}
            onDelete={deleteItem}
            render={(item, index) => (
              <>
                <div className="field-grid skill-grid">
                  <TextField label="Skill" value={item.name} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("skills", index, "name", value)} />
                  <label className="field-label">
                    Proficiency
                    <select
                      value={item.proficiency ?? ""}
                      disabled={profileLocked || mutationBusy}
                      onChange={(event) => updateItem("skills", index, "proficiency", event.target.value || null)}
                    >
                      <option value="">Not assessed</option>
                      {proficiencyOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                </div>
                <Evidence item={item} />
              </>
            )}
          />
          <ProfileSection<Experience>
            title="Experiences"
            section="experiences"
            items={profile.experiences}
            locked={profileLocked || mutationBusy}
            onAdd={addItem}
            onDelete={deleteItem}
            render={(item, index) => (
              <>
                <div className="field-grid">
                  <TextField label="Role / title" value={item.title} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "title", value)} />
                  <TextField label="Organization" value={item.organization} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "organization", value)} />
                  <TextField label="Dates" value={item.dates} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "dates", value)} />
                  <TextField label="Description" value={item.description} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "description", value)} multiline />
                  <label className="field-label">
                    Experience type
                    <select
                      value={item.experience_type}
                      disabled={profileLocked || mutationBusy}
                      onChange={(event) => updateItem("experiences", index, "experience_type", event.target.value)}
                    >
                      {experienceTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                </div>
                <Evidence item={item} />
              </>
            )}
          />
          <ProfileSection<Certification>
            title="Certifications"
            section="certifications"
            items={profile.certifications}
            locked={profileLocked || mutationBusy}
            onAdd={addItem}
            onDelete={deleteItem}
            render={(item, index) => (
              <>
                <div className="field-grid">
                  <TextField label="Certification" value={item.name} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("certifications", index, "name", value)} />
                  <TextField label="Issuer" value={item.issuer} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("certifications", index, "issuer", value)} />
                  <TextField label="Date" value={item.date} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("certifications", index, "date", value)} />
                  <TextField label="Score" value={item.score} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("certifications", index, "score", value)} />
                  <TextField label="Status" value={item.status} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("certifications", index, "status", value)} />
                </div>
                <Evidence item={item} />
              </>
            )}
          />
          <div className="profile-actions">
            <button type="button" className="button-secondary" onClick={saveDraft} disabled={profileLocked || mutationBusy}>
              {saving === "save" ? "Saving..." : "Save Draft"}
            </button>
            <button type="button" onClick={confirmProfile} disabled={profileLocked || mutationBusy}>
              {saving === "confirm" ? "Confirming..." : "Confirm Profile"}
            </button>
          </div>
          {profileCanEditCareerPreferences(profile) && (
            <section className="career-preferences" aria-label="Career Preferences">
              <h3>Career Preferences</h3>
              <p className="profile-note">Choose the two priorities that matter most for your next career decision.</p>
              <div className="preference-grid">
                {CAREER_PREFERENCE_OPTIONS.map((option) => {
                  const order = preferenceDraft.priority_order.indexOf(option.value);
                  const selected = order !== -1;
                  const full = preferenceDraft.priority_order.length >= 2;
                  return (
                    <button
                      key={option.value}
                      type="button"
                      className={selected ? "preference-card selected" : "preference-card"}
                      aria-pressed={selected}
                      disabled={savingPreferences || (full && !selected)}
                      onClick={() => selectPreference(option.value)}
                    >
                      <span className="preference-order">{selected ? "#" + (order + 1) : ""}</span>
                      <span>{option.label}</span>
                    </button>
                  );
                })}
              </div>
              <label className="field-label">
                每周可用于职业准备/学习的时间（小时）
                <input
                  type="number"
                  min={1}
                  max={60}
                  step={1}
                  value={preferenceDraft.weekly_hours}
                  disabled={savingPreferences}
                  onChange={(event) => {
                    setRoleExploration(null);
                    setPreferenceDraft((current) => ({ ...current, weekly_hours: event.target.value }));
                  }}
                />
              </label>
              <button
                type="button"
                onClick={savePreferences}
                disabled={savingPreferences || !isCareerPreferencesDraftValid(preferenceDraft.priority_order, preferenceDraft.weekly_hours)}
              >
                {savingPreferences ? "Saving..." : "Save preferences"}
              </button>
              <button type="button" className="button-secondary" onClick={exploreRoles} disabled={!explorationReady || loadingExploration || creatingExploration}>
                {creatingExploration ? "正在探索..." : "下一步：探索适合我的岗位"}
              </button>
              {loadingExploration && <p className="profile-note">正在加载最近一次探索结果...</p>}
              {roleExploration && (
                <section className="role-exploration" aria-label="Role exploration results">
                  <div className="section-heading">
                    <div><p className="section-kicker">Exploratory guidance</p><h3>适合探索的岗位方向</h3></div>
                    <span className="role-version">{roleExploration.role_profile_version}</span>
                  </div>
                  <div className="role-card-grid">
                    {roleExplorationViewData(roleExploration).map((item) => (
                      <article className="role-card" key={item.role_code}>
                        <div className="role-card-heading"><h4>{item.role_name}</h4><span className={`role-level ${item.level.toLowerCase()}`}>{ROLE_EXPLORATION_LEVEL_LABELS[item.level]}</span></div>
                        <div className="role-card-list"><strong>为什么</strong><ul>{item.reasons.map((reason, index) => <li key={`${item.role_code}-reason-${index}`}>{reason}</li>)}</ul></div>
                        {item.concerns.length > 0 && <div className="role-card-list concern"><strong>需要留意</strong><ul>{item.concerns.map((concern, index) => <li key={`${item.role_code}-concern-${index}`}>{concern}</li>)}</ul></div>}
                        <p className="role-refs"><span>Profile evidence</span>{item.evidence_refs.join(", ")}</p>
                        <p className="role-refs"><span>Preference refs</span>{item.preference_refs.join(", ") || "—"}</p>
                      </article>
                    ))}
                  </div>
                  <p className="role-disclaimer">{ROLE_EXPLORATION_DISCLAIMER}</p>
                </section>
              )}
            </section>
          )}
        </section>
      )}
    </main>
  );
}

function newItem(section: EditableSection): Profile[EditableSection][number] {
  const base = { evidence_text: null, source_type: "USER_ENTERED" as const };
  if (section === "education") return createEmptyEducation();
  if (section === "skills") return { ...base, name: "", proficiency: null };
  if (section === "experiences") return { ...base, title: "", organization: null, dates: null, description: null, experience_type: "OTHER" as const };
  return { ...base, name: "", issuer: null, date: null, score: null, status: null };
}

function ProfileSection<T extends ProfileItem>({
  title,
  section,
  items,
  locked,
  onAdd,
  onDelete,
  render,
}: {
  title: string;
  section: EditableSection;
  items: T[];
  locked: boolean;
  onAdd: (section: EditableSection) => void;
  onDelete: (section: EditableSection, index: number) => void;
  render: (item: T, index: number) => ReactNode;
}) {
  return (
    <section className="profile-section">
      <div className="section-heading">
        <h3>{title}</h3>
        <button type="button" className="text-button" onClick={() => onAdd(section)} disabled={locked}>+ Add</button>
      </div>
      {items.length ? items.map((item, index) => (
        <article className="profile-item" key={`${section}-${item.id ?? `new-${index}`}`}>
          {render(item, index)}
          <button type="button" className="delete-button" onClick={() => onDelete(section, index)} disabled={locked}>Delete</button>
        </article>
      )) : <p className="empty">No entries yet. Add one if it belongs in your profile.</p>}
    </section>
  );
}

function TextField({ label, value, disabled, onChange, multiline = false }: { label: string; value: string | null; disabled: boolean; onChange: (value: string | null) => void; multiline?: boolean }) {
  const props = { value: value ?? "", disabled, onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value) };
  return <label className="field-label">{label}{multiline ? <textarea {...props} rows={3} /> : <input {...props} />}</label>;
}

function Evidence({ item }: { item: ProfileItem }) {
  return item.evidence_text ? <p className="evidence"><span>Resume evidence</span>{item.evidence_text}</p> : <p className="evidence user-provided"><span>Provenance</span>User provided</p>;
}
