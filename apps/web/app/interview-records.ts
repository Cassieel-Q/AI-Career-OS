import { readApiPayload } from "./profile-flow.ts";
import { MISSION_API_BASE_URL, PROFILE_STORAGE_KEY } from "./missions.ts";

export { MISSION_API_BASE_URL, PROFILE_STORAGE_KEY };

export const INTERVIEW_ROUNDS = ["一面", "二面", "三面", "其他"] as const;
export type InterviewRound = (typeof INTERVIEW_ROUNDS)[number];

export type InterviewRecordItem = {
  id: string;
  record_id: string;
  sort_order: number;
  question: string;
  context: string | null;
  my_answer: string;
  evaluation: {
    score?: number | null;
    reference_answer?: string | null;
    strong_points?: string[];
    weak_points?: string[];
    gap_type?: string | null;
    why?: string | null;
    recommended_next_action?: string | null;
    [key: string]: unknown;
  } | null;
  created_at: string;
};

export type InterviewRecord = {
  id: string;
  profile_id: string;
  mission_id: string | null;
  company: string;
  role: string | null;
  interview_round: string;
  interviewed_on: string;
  notes: string | null;
  status: string;
  strong_points: string[];
  weak_points: string[];
  gap_type: string | null;
  gap_why: string | null;
  recommended_next_action: string | null;
  coaching: {
    title?: string;
    summary?: string;
    questions?: string[];
    steps?: string[];
    learning?: string[];
    expected_outputs?: string[];
    generated_by?: string;
    [key: string]: unknown;
  } | null;
  items: InterviewRecordItem[];
  created_at: string;
  updated_at: string;
  evaluated: boolean;
};

export type InterviewRecordCompanyGroup = {
  company: string;
  company_key: string;
  record_count: number;
  latest_interviewed_on: string | null;
  rounds: string[];
  records: InterviewRecord[];
};

export type InterviewRecordList = {
  records: InterviewRecord[];
  companies: InterviewRecordCompanyGroup[];
};

export type InterviewRecordItemInput = {
  question: string;
  context?: string | null;
  my_answer: string;
  sort_order?: number;
};

export type InterviewRecordCreateInput = {
  company: string;
  role?: string | null;
  interview_round: InterviewRound | string;
  interviewed_on: string;
  notes?: string | null;
  mission_id?: string | null;
  items: InterviewRecordItemInput[];
};

type Requester = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export function readStoredProfileId(): string {
  if (typeof window === "undefined") return "";
  return (window.localStorage.getItem(PROFILE_STORAGE_KEY) || "").trim();
}

export function companyKeyFromName(company: string): string {
  return encodeURIComponent(company.trim());
}

export function companyNameFromKey(companyKey: string): string {
  try {
    return decodeURIComponent(companyKey);
  } catch {
    return companyKey;
  }
}

export async function listInterviewRecords(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: Requester = fetch,
): Promise<InterviewRecordList> {
  const response = await request(
    `${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/interview-records`,
  );
  return readApiPayload<InterviewRecordList>(response);
}

export async function createInterviewRecord(
  profileId: string,
  payload: InterviewRecordCreateInput,
  apiUrl = MISSION_API_BASE_URL,
  request: Requester = fetch,
): Promise<InterviewRecord> {
  const response = await request(
    `${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/interview-records`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
  );
  return readApiPayload<InterviewRecord>(response);
}

export async function readInterviewRecord(
  recordId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: Requester = fetch,
): Promise<InterviewRecord> {
  const response = await request(`${apiUrl}/api/v1/interview-records/${encodeURIComponent(recordId)}`);
  return readApiPayload<InterviewRecord>(response);
}

export async function evaluateInterviewRecord(
  recordId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: Requester = fetch,
): Promise<InterviewRecord> {
  const response = await request(
    `${apiUrl}/api/v1/interview-records/${encodeURIComponent(recordId)}/evaluate`,
    { method: "POST" },
  );
  return readApiPayload<InterviewRecord>(response);
}
