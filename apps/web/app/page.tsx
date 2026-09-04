"use client";

import { ChangeEvent, FormEvent, useState } from "react";
import type { ReactNode } from "react";

type ProfileStatus = "DRAFT" | "CONFIRMED";
type Proficiency = "AWARE" | "BASIC" | "PROJECT_READY" | "PROFICIENT";
type SourceType = "AI_EXTRACTED" | "USER_ENTERED" | "USER_EDITED";

type ProfileItem = {
  id?: string;
  evidence_text: string | null;
  source_type: SourceType;
};

type Education = ProfileItem & {
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  dates: string | null;
};

type Skill = ProfileItem & {
  name: string;
  proficiency: Proficiency | null;
};

type Experience = ProfileItem & {
  title: string;
  organization: string | null;
  dates: string | null;
  description: string | null;
};

type Certification = ProfileItem & {
  name: string;
  issuer: string | null;
  date: string | null;
};

type Profile = {
  profile_id: string;
  status: ProfileStatus;
  created_at: string;
  updated_at: string;
  education: Education[];
  skills: Skill[];
  experiences: Experience[];
  certifications: Certification[];
};

type EditableSection = "education" | "skills" | "experiences" | "certifications";

const proficiencyOptions: Array<{ value: Proficiency; label: string }> = [
  { value: "AWARE", label: "AWARE" },
  { value: "BASIC", label: "BASIC" },
  { value: "PROJECT_READY", label: "PROJECT_READY" },
  { value: "PROFICIENT", label: "PROFICIENT" },
];

const apiUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<"save" | "confirm" | null>(null);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setProfile(null);
    setError("");
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
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`${apiUrl}/api/v1/resumes`, {
        method: "POST",
        body,
      });
      const payload = await readPayload(response);
      setProfile(payload as Profile);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Resume upload failed.");
    } finally {
      setLoading(false);
    }
  }

  function updateItem(section: EditableSection, index: number, field: string, value: string | null) {
    setProfile((current) => {
      if (!current || current.status === "CONFIRMED") return current;
      const items = current[section].map((item, itemIndex) =>
        itemIndex === index ? { ...item, [field]: value } : item,
      );
      return { ...current, [section]: items } as Profile;
    });
  }

  function addItem(section: EditableSection) {
    setProfile((current) => {
      if (!current || current.status === "CONFIRMED") return current;
      const item = newItem(section);
      return { ...current, [section]: [...current[section], item] } as Profile;
    });
  }

  function deleteItem(section: EditableSection, index: number) {
    setProfile((current) => {
      if (!current || current.status === "CONFIRMED") return current;
      return {
        ...current,
        [section]: current[section].filter((_, itemIndex) => itemIndex !== index),
      } as Profile;
    });
  }

  async function saveDraft() {
    if (!profile || profile.status === "CONFIRMED") return;
    setSaving("save");
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/profiles/${profile.profile_id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(toUpdatePayload(profile)),
      });
      const payload = await readPayload(response);
      setProfile(payload as Profile);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Profile could not be saved.");
    } finally {
      setSaving(null);
    }
  }

  async function confirmProfile() {
    if (!profile || profile.status === "CONFIRMED") return;
    setSaving("confirm");
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/profiles/${profile.profile_id}/confirm`, {
        method: "POST",
      });
      const payload = await readPayload(response);
      setProfile(payload as Profile);
    } catch (confirmError) {
      setError(confirmError instanceof Error ? confirmError.message : "Profile could not be confirmed.");
    } finally {
      setSaving(null);
    }
  }

  const profileLocked = profile?.status === "CONFIRMED";
  const mutationBusy = saving !== null;

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
        <button type="submit" disabled={loading || mutationBusy}>
          {loading ? "Extracting..." : "Upload resume"}
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
        </section>
      )}
    </main>
  );
}

function newItem(section: EditableSection): Profile[EditableSection][number] {
  const base = { evidence_text: null, source_type: "USER_ENTERED" as const };
  if (section === "education") return { ...base, institution: "", degree: null, field_of_study: null, dates: null };
  if (section === "skills") return { ...base, name: "", proficiency: null };
  if (section === "experiences") return { ...base, title: "", organization: null, dates: null, description: null };
  return { ...base, name: "", issuer: null, date: null };
}

function toUpdatePayload(profile: Profile) {
  const stripId = <T extends ProfileItem>(item: T) => {
    const { id, ...rest } = item;
    return id ? { id, ...rest } : rest;
  };
  return {
    education: profile.education.map(stripId),
    skills: profile.skills.map(stripId),
    experiences: profile.experiences.map(stripId),
    certifications: profile.certifications.map(stripId),
  };
}

async function readPayload(response: Response): Promise<unknown> {
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? "Request failed.");
  return payload;
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
  const props = { value: value ?? "", disabled, onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onChange(event.target.value || null) };
  return <label className="field-label">{label}{multiline ? <textarea {...props} rows={3} /> : <input {...props} />}</label>;
}

function Evidence({ item }: { item: ProfileItem }) {
  return item.evidence_text ? <p className="evidence"><span>Resume evidence</span>{item.evidence_text}</p> : <p className="evidence user-provided"><span>Provenance</span>User provided</p>;
}
