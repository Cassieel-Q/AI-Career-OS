import { MISSION_API_BASE_URL } from "./missions.ts";

/** 面试版本一致性（指令 5.3）：面试默认读取**实际投递**的那一版。 */

export type InterviewResume = {
  source: "delivered_snapshot" | "delivered_application" | "resume_studio" | "target_resume" | "none";
  label: string;
  warning: string | null;
  /** true 表示这份内容来自真实投递（面试官看到的就是它）。 */
  delivered: boolean;
  application_id: string | null;
  snapshot_id: string | null;
  studio_revision: number | null;
  delivered_at: string | null;
  content_hash: string | null;
  has_pdf: boolean;
  bullets: Array<{ source_experience_id?: string | null; text: string; status?: string | null }>;
  versions: InterviewResumeVersion[];
};

export type InterviewResumeVersion = {
  application_id: string;
  status: string;
  applied_at: string | null;
  channel: string;
  studio_revision: number | null;
  has_snapshot: boolean;
  snapshot_id: string | null;
  label: string;
};

const root = (missionId: string) =>
  `${MISSION_API_BASE_URL}/api/v1/job-missions/${encodeURIComponent(missionId)}`;

type Requester = typeof fetch;

async function request<T>(url: string, init?: RequestInit, send: Requester = fetch): Promise<T> {
  const response = await send(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `面试版本接口请求失败（${response.status}）`);
  }
  return (await response.json()) as T;
}

export const readInterviewResume = (
  missionId: string,
  applicationId?: string | null,
  send: Requester = fetch,
) =>
  request<InterviewResume>(
    `${root(missionId)}/interview-resume${applicationId ? `?application_id=${encodeURIComponent(applicationId)}` : ""}`,
    undefined,
    send,
  );

export const readDeliveryVersions = (missionId: string, send: Requester = fetch) =>
  request<{ mission_id: string; versions: InterviewResumeVersion[] }>(
    `${root(missionId)}/delivery-versions`,
    undefined,
    send,
  );

export const NO_DELIVERY_LABEL = "尚无正式投递版本，当前使用准备中的简历。";

/** 面试准备用的简历是否来自真实投递（决定横幅语气）。 */
export const isDelivered = (resume: InterviewResume | null): boolean =>
  Boolean(resume && (resume.delivered || resume.source === "delivered_snapshot" || resume.source === "delivered_application"));

/** 横幅文案：投递版说清是哪一次投递，未投递时明确标注。 */
export function interviewVersionBanner(resume: InterviewResume | null): {
  tone: "delivered" | "preparing" | "fallback";
  title: string;
  detail: string;
} {
  if (!resume || resume.source === "none") {
    return { tone: "fallback", title: "这个岗位还没有可用来准备面试的简历版本", detail: "先在简历工作台生成并确认一版。" };
  }
  if (resume.source === "delivered_snapshot") {
    return {
      tone: "delivered",
      title: `按实际投递的版本准备（修订版 v${resume.studio_revision ?? "—"}）`,
      detail: `${resume.label}${resume.has_pdf ? " · 可下载投递时的 PDF 快照" : ""}。投递之后新增的内容不会混入本轮面试。`,
    };
  }
  if (resume.source === "delivered_application") {
    return {
      tone: "delivered",
      title: `按投递记录绑定的版本准备（修订版 v${resume.studio_revision ?? "—"}）`,
      detail: resume.warning ?? resume.label,
    };
  }
  return { tone: "preparing", title: NO_DELIVERY_LABEL, detail: "投递后本轮会自动切换到你真正投出去的那一版。" };
}
