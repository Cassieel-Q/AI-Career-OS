"use client";

import { useCallback, useEffect, useState } from "react";
import type { ChangeEvent, ReactNode } from "react";

import {
  confirmProfileRequest,
  createEmptyEducation,
  normalizeProfile,
  saveProfileRequest,
  validateProfileForSave,
} from "./profile-flow.ts";
import type {
  Certification,
  Education,
  Experience,
  ExperienceType,
  Profile,
  ProfileItem,
  Proficiency,
  Skill,
} from "./profile-flow.ts";
import type { WorkflowNextAction, WorkflowStepControls } from "./workflow-route.tsx";

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

export function ProfileStep({ profile: serverProfile, controls }: { profile: Profile; controls: WorkflowStepControls }) {
  const [profile, setProfile] = useState<Profile>(serverProfile);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState<"draft" | "confirm" | null>(null);
  const [error, setError] = useState("");
  const profileLocked = profile.status === "CONFIRMED";
  const validationError = validateProfileForSave(profile);
  const setNextReady = controls.setNextReady;
  const setNextAction = controls.setNextAction;

  useEffect(() => {
    setProfile(serverProfile);
    setDirty(false);
    setError("");
  }, [serverProfile]);

  useEffect(() => {
    setNextReady(Boolean(profile) && (profileLocked || validationError === null));
  }, [setNextReady, profile, profileLocked, validationError]);

  function updateItem(section: EditableSection, index: number, field: string, value: string | null) {
    if (profileLocked) return;
    setDirty(true);
    setProfile((current) => {
      if (current.status === "CONFIRMED") return current;
      const items = current[section].map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item);
      return { ...current, [section]: items } as Profile;
    });
  }

  function addItem(section: EditableSection) {
    if (profileLocked) return;
    setDirty(true);
    setProfile((current) => ({ ...current, [section]: [...current[section], newItem(section)] }) as Profile);
  }

  function deleteItem(section: EditableSection, index: number) {
    if (profileLocked) return;
    setDirty(true);
    setProfile((current) => ({
      ...current,
      [section]: current[section].filter((_, itemIndex) => itemIndex !== index),
    }) as Profile);
  }

  function updateEducationCourses(index: number, value: string) {
    if (profileLocked) return;
    const relevant_courses = value
      .split(/[,，、;；]/)
      .map((course) => course.trim())
      .filter(Boolean);
    setDirty(true);
    setProfile((current) => ({
      ...current,
      education: current.education.map((item, itemIndex) => itemIndex === index ? { ...item, relevant_courses } : item),
    }));
  }

  async function saveDraft() {
    if (profileLocked || saving) return;
    if (validationError) {
      setError(validationError);
      return;
    }
    setSaving("draft");
    setError("");
    try {
      const saved = normalizeProfile(await saveProfileRequest(profile, controls.apiUrl));
      setProfile(saved);
      setDirty(false);
      await controls.refresh();
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Profile could not be saved.");
    } finally {
      setSaving(null);
    }
  }

  const confirmAndContinue = useCallback<WorkflowNextAction>(async () => {
    if (profile.status === "CONFIRMED") return true;
    const message = validateProfileForSave(profile);
    if (message) {
      setError(message);
      return false;
    }
    setSaving("confirm");
    setError("");
    try {
      const confirmed = normalizeProfile(await confirmProfileRequest(profile, dirty, controls.apiUrl));
      setProfile(confirmed);
      setDirty(false);
      return true;
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "Profile could not be confirmed.");
      return false;
    } finally {
      setSaving(null);
    }
  }, [controls.apiUrl, dirty, profile]);

  useEffect(() => {
    setNextAction(confirmAndContinue);
    return () => setNextAction(null);
  }, [confirmAndContinue, setNextAction]);

  const mutationBusy = saving !== null || controls.busy;

  return (
    <div className="workflow-step-content">
      <div className="step-heading">
        <p className="section-kicker">Step 1 · Profile confirmation</p>
        <h1 id="workflow-step-title">确认你的 Profile</h1>
        <p className="summary">AI 提取的内容仍是待确认事实。请核对基础信息、教育、经历和技能，并查看每条事实的简历证据。</p>
      </div>
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
            ? "This profile is confirmed. Its evidence-backed facts are ready for career planning."
            : "AI facts keep their resume evidence. Edit or supplement anything before confirming it as yours."}
        </p>

        <ProfileSection<Education> title="Education" section="education" items={profile.education} locked={profileLocked || mutationBusy} onAdd={addItem} onDelete={deleteItem} render={(item, index) => (
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
        )} />

        <ProfileSection<Skill> title="Skills" section="skills" items={profile.skills} locked={profileLocked || mutationBusy} onAdd={addItem} onDelete={deleteItem} render={(item, index) => (
          <>
            <div className="field-grid skill-grid">
              <TextField label="Skill" value={item.name} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("skills", index, "name", value)} />
              <label className="field-label">
                Proficiency
                <select value={item.proficiency ?? ""} disabled={profileLocked || mutationBusy} onChange={(event) => updateItem("skills", index, "proficiency", event.target.value || null)}>
                  <option value="">Not assessed</option>
                  {proficiencyOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
            <Evidence item={item} />
          </>
        )} />

        <ProfileSection<Experience> title="Experiences" section="experiences" items={profile.experiences} locked={profileLocked || mutationBusy} onAdd={addItem} onDelete={deleteItem} render={(item, index) => (
          <>
            <div className="field-grid">
              <TextField label="Role / title" value={item.title} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "title", value)} />
              <TextField label="Organization" value={item.organization} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "organization", value)} />
              <TextField label="Dates" value={item.dates} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "dates", value)} />
              <TextField label="Description" value={item.description} disabled={profileLocked || mutationBusy} onChange={(value) => updateItem("experiences", index, "description", value)} multiline />
              <label className="field-label">
                Experience type
                <select value={item.experience_type} disabled={profileLocked || mutationBusy} onChange={(event) => updateItem("experiences", index, "experience_type", event.target.value)}>
                  {experienceTypeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </div>
            <Evidence item={item} />
          </>
        )} />

        <ProfileSection<Certification> title="Certifications" section="certifications" items={profile.certifications} locked={profileLocked || mutationBusy} onAdd={addItem} onDelete={deleteItem} render={(item, index) => (
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
        )} />

        {!profileLocked && validationError && <p className="profile-note">请先修正：{validationError}</p>}
        {error && <p className="message error" role="alert">{error}</p>}
        <div className="profile-actions">
          <button type="button" className="button-secondary" onClick={() => void saveDraft()} disabled={profileLocked || mutationBusy || !dirty}>
            {saving === "draft" ? "Saving…" : "Save Draft"}
          </button>
        </div>
      </section>
    </div>
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

function TextField({ label, value, disabled, onChange, multiline = false }: {
  label: string;
  value: string | null;
  disabled: boolean;
  onChange: (value: string | null) => void;
  multiline?: boolean;
}) {
  const props = {
    value: value ?? "",
    disabled,
    onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value),
  };
  return <label className="field-label">{label}{multiline ? <textarea {...props} rows={3} /> : <input {...props} />}</label>;
}

function Evidence({ item }: { item: ProfileItem }) {
  return item.evidence_text
    ? <p className="evidence"><span>Resume evidence</span>{item.evidence_text}</p>
    : <p className="evidence user-provided"><span>Provenance</span>User provided</p>;
}
