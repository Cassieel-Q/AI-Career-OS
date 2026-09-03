"use client";

import { ChangeEvent, FormEvent, ReactNode, useState } from "react";

type EvidenceItem = { evidence_text: string };
type Profile = {
  education: Array<
    EvidenceItem & { institution: string; degree?: string | null }
  >;
  skills: Array<EvidenceItem & { name: string; proficiency: null }>;
  experiences: Array<
    EvidenceItem & { title: string; organization?: string | null }
  >;
  certifications: Array<
    EvidenceItem & { name: string; issuer?: string | null }
  >;
};

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

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
      const payload = await response.json();
      if (!response.ok)
        throw new Error(payload.detail ?? "Resume upload failed.");
      setProfile(payload as Profile);
    } catch (uploadError) {
      setError(
        uploadError instanceof Error
          ? uploadError.message
          : "Resume upload failed.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell">
      <p className="eyebrow">AI Career OS / Resume intake</p>
      <h1>Build a draft profile from your resume.</h1>
      <p className="summary">
        Upload a text-based PDF. Extracted facts keep their source evidence for
        review.
      </p>
      <form className="upload-panel" onSubmit={upload}>
        <label htmlFor="resume">Resume PDF</label>
        <input
          id="resume"
          type="file"
          accept="application/pdf,.pdf"
          onChange={chooseFile}
        />
        <button type="submit" disabled={loading}>
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
        <section className="profile" aria-label="Draft Profile">
          <h2>Draft Profile</h2>
          <ProfileSection
            title="Education"
            items={profile.education}
            render={(item) => (
              <>
                <strong>{item.institution}</strong>
                {item.degree && ` · ${item.degree}`}
              </>
            )}
          />
          <ProfileSection
            title="Skills"
            items={profile.skills}
            render={(item) => <strong>{item.name}</strong>}
          />
          <ProfileSection
            title="Experiences"
            items={profile.experiences}
            render={(item) => (
              <>
                <strong>{item.title}</strong>
                {item.organization && ` · ${item.organization}`}
              </>
            )}
          />
          <ProfileSection
            title="Certifications"
            items={profile.certifications}
            render={(item) => (
              <>
                <strong>{item.name}</strong>
                {item.issuer && ` · ${item.issuer}`}
              </>
            )}
          />
        </section>
      )}
    </main>
  );
}

function ProfileSection<T extends EvidenceItem>({
  title,
  items,
  render,
}: {
  title: string;
  items: T[];
  render: (item: T) => ReactNode;
}) {
  return (
    <section className="profile-section">
      <h3>{title}</h3>
      {items.length ? (
        <ul>
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>
              {render(item)}
              <span>{item.evidence_text}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="empty">No entries found.</p>
      )}
    </section>
  );
}
