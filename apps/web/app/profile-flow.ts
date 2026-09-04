export type ProfileStatus = "DRAFT" | "CONFIRMED";
export type Proficiency = "AWARE" | "BASIC" | "PROJECT_READY" | "PROFICIENT";
export type SourceType = "AI_EXTRACTED" | "USER_ENTERED" | "USER_EDITED";

export type ProfileItem = {
  id?: string;
  evidence_text: string | null;
  source_type: SourceType;
};

export type Education = ProfileItem & {
  institution: string;
  degree: string | null;
  field_of_study: string | null;
  dates: string | null;
};

export type Skill = ProfileItem & {
  name: string;
  proficiency: Proficiency | null;
};

export type Experience = ProfileItem & {
  title: string;
  organization: string | null;
  dates: string | null;
  description: string | null;
};

export type Certification = ProfileItem & {
  name: string;
  issuer: string | null;
  date: string | null;
};

export type Profile = {
  profile_id: string;
  status: ProfileStatus;
  created_at: string;
  updated_at: string;
  education: Education[];
  skills: Skill[];
  experiences: Experience[];
  certifications: Certification[];
};

export type ProfileUpdatePayload = {
  education: Array<{
    id?: string;
    institution: string;
    degree: string | null;
    field_of_study: string | null;
    dates: string | null;
  }>;
  skills: Array<{ id?: string; name: string; proficiency: Proficiency | null }>;
  experiences: Array<{
    id?: string;
    title: string;
    organization: string | null;
    dates: string | null;
    description: string | null;
  }>;
  certifications: Array<{ id?: string; name: string; issuer: string | null; date: string | null }>;
};

export type ProfileRequester = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export function toUpdatePayload(profile: Profile): ProfileUpdatePayload {
  return {
    // evidence_text and source_type are intentionally omitted: existing
    // evidence is server-owned and new rows default to USER_ENTERED server-side.
    education: profile.education.map(({ id, institution, degree, field_of_study, dates }) => ({
      ...(id ? { id } : {}),
      institution,
      degree,
      field_of_study,
      dates,
    })),
    skills: profile.skills.map(({ id, name, proficiency }) => ({
      ...(id ? { id } : {}),
      name,
      proficiency,
    })),
    experiences: profile.experiences.map(({ id, title, organization, dates, description }) => ({
      ...(id ? { id } : {}),
      title,
      organization,
      dates,
      description,
    })),
    certifications: profile.certifications.map(({ id, name, issuer, date }) => ({
      ...(id ? { id } : {}),
      name,
      issuer,
      date,
    })),
  };
}

export function validateProfileForSave(profile: Profile): string | null {
  const requiredFields: Array<[keyof Profile, string, string]> = [
    ["education", "institution", "School"],
    ["skills", "name", "Skill"],
    ["experiences", "title", "Role / title"],
    ["certifications", "name", "Certification"],
  ];
  for (const [section, field, label] of requiredFields) {
    const items = profile[section] as Array<Record<string, unknown>>;
    const itemIndex = items.findIndex((item) => typeof item[field] !== "string" || !item[field].trim());
    if (itemIndex !== -1) return `${section[0].toUpperCase()}${section.slice(1)} item ${itemIndex + 1}: ${label} is required.`;
  }
  return null;
}

export async function saveProfileRequest(
  profile: Profile,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<Profile> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profile.profile_id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(toUpdatePayload(profile)),
  });
  return readApiPayload<Profile>(response);
}

export async function confirmProfileRequest(
  profile: Profile,
  dirty: boolean,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<Profile> {
  const persistedProfile = dirty ? await saveProfileRequest(profile, apiUrl, request) : profile;
  const response = await request(`${apiUrl}/api/v1/profiles/${persistedProfile.profile_id}/confirm`, {
    method: "POST",
  });
  return readApiPayload<Profile>(response);
}

export function getProfileIdFromSearch(search: string): string | null {
  return new URLSearchParams(search).get("profile_id");
}

export function profileHref(currentHref: string, profileId: string): string {
  const url = new URL(currentHref, "http://localhost");
  url.searchParams.set("profile_id", profileId);
  return `${url.pathname}${url.search}${url.hash}`;
}

export async function readApiPayload<T>(response: Response): Promise<T> {
  const raw = await response.text();
  let payload: unknown = null;
  if (raw) {
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = { detail: raw };
    }
  }
  if (!response.ok) throw new Error(formatApiError(payload, response.status));
  return payload as T;
}

function formatApiError(payload: unknown, status: number): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = payload.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const messages = detail.map((entry) => {
        if (!entry || typeof entry !== "object") return String(entry);
        const record = entry as { loc?: unknown; msg?: unknown };
        const location = Array.isArray(record.loc) ? record.loc.join(".") : "";
        const message = typeof record.msg === "string" ? record.msg : JSON.stringify(entry);
        return location ? `${location}: ${message}` : message;
      });
      return messages.join("; ") || `Request failed (HTTP ${status}).`;
    }
    return JSON.stringify(detail);
  }
  return `Request failed (HTTP ${status}).`;
}
