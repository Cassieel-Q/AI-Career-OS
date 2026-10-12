"use client";

import { MISSION_API_BASE_URL } from "./missions.ts";
import { readApiPayload } from "./profile-flow.ts";

export type AssistantSurface = "page" | "orb";

export type AssistantConversation = {
  id: string;
  surface: AssistantSurface;
  title: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls?: Array<{ name: string; changed: boolean; summary: string }> | null;
  sources?: Array<{ title?: string; url?: string; snippet?: string; error?: string }> | null;
  created_at?: string | null;
};

export type ChatRequest = {
  content: string;
  profile_id?: string | null;
  mission_id?: string | null;
  /** 第三阶段：从岗位面试页进入时自动带上岗位版简历，用户无需重新选择。 */
  target_resume_id?: string | null;
  route?: string | null;
  web_search: boolean;
  allow_write: boolean;
  reasoning_effort: "low" | "medium" | "high";
};

export type ResolvedInterviewContext = {
  intent: string;
  company?: string | null;
  role?: string | null;
  mission_id?: string | null;
  target_resume_id?: string | null;
  context_confidence: number;
  needs_clarification: boolean;
  reason: string;
  jd_in_message: boolean;
  crash_prep: boolean;
  candidates: Array<{ mission_id: string; company: string; role: string; display_name: string }>;
  missing_context: string[];
};

export type InterviewContextSummary = {
  company?: string | null;
  role?: string | null;
  mission_id?: string | null;
  resume_version?: number | null;
  resume_status?: string | null;
  experience_count: number;
  confirmed_claims_count: number;
  has_interview_intel: boolean;
  missing_context: string[];
};

export type InterviewPrepPlan = {
  mode: "FULL_PREP" | "CRASH_PREP";
  steps: Array<{ step: string; title: string; tool?: string | null; status: string; reasons: string[]; produces: string }>;
  blocked_steps: string[];
  sections: Array<{ key: string; title: string; items: unknown[]; grounding?: string; note?: string | null }>;
  missing_context: string[];
  grounding_note: string;
  question_count: number;
};

export type InterviewContextResult = {
  resolved: ResolvedInterviewContext;
  summary: InterviewContextSummary | null;
  prep: InterviewPrepPlan | null;
};

export type StreamEvent =
  | { type: "start"; conversation_id: string }
  | { type: "delta"; text: string }
  | { type: "tool"; name: string; changed: boolean; ok?: boolean; error?: string | null; summary: string }
  | { type: "sources"; sources: Array<Record<string, unknown>> }
  | { type: "degraded"; reasons: string[] }
  | { type: "done"; message: AssistantMessage }
  | { type: "error"; message: string };

const api = MISSION_API_BASE_URL;

export async function listConversations(surface: AssistantSurface): Promise<AssistantConversation[]> {
  const response = await fetch(`${api}/api/v1/assistant/conversations?surface=${surface}`);
  return readApiPayload<AssistantConversation[]>(response);
}

export async function createConversation(surface: AssistantSurface): Promise<AssistantConversation> {
  const response = await fetch(`${api}/api/v1/assistant/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ surface }),
  });
  return readApiPayload<AssistantConversation>(response);
}

export async function getConversation(id: string, surface: AssistantSurface): Promise<{ messages: AssistantMessage[] } & AssistantConversation> {
  const response = await fetch(`${api}/api/v1/assistant/conversations/${encodeURIComponent(id)}?surface=${surface}`);
  return readApiPayload(response);
}

export async function deleteConversation(id: string, surface: AssistantSurface): Promise<void> {
  await fetch(`${api}/api/v1/assistant/conversations/${encodeURIComponent(id)}?surface=${surface}`, { method: "DELETE" });
}

/** 解析当前面试上下文（第一~四阶段）：岗位 / 目标简历 / 准备流程。 */
export async function resolveInterviewContext(payload: {
  message?: string;
  profile_id?: string | null;
  mission_id?: string | null;
  target_resume_id?: string | null;
  route?: string | null;
}): Promise<InterviewContextResult> {
  const response = await fetch(`${api}/api/v1/assistant/interview-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: payload.message ?? "",
      profile_id: payload.profile_id ?? null,
      mission_id: payload.mission_id ?? null,
      target_resume_id: payload.target_resume_id ?? null,
      route: payload.route ?? null,
    }),
  });
  return readApiPayload<InterviewContextResult>(response);
}

/** 流式问答：逐事件回调。返回最终 assistant 消息。 */
export async function streamChat(
  conversationId: string,
  payload: ChatRequest,
  onEvent: (event: StreamEvent) => void,
): Promise<AssistantMessage> {
  const response = await fetch(`${api}/api/v1/assistant/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => "");
    throw new Error(text || `请求失败（${response.status}）`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalMessage: AssistantMessage | null = null;
  let serverError = "";

  const feed = (chunk: string) => {
    buffer += chunk;
    let index: number;
    while ((index = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 2);
      if (!raw.startsWith("data:")) continue;
      const json = raw.slice(5).trim();
      if (!json) continue;
      try {
        const event = JSON.parse(json) as StreamEvent;
        if (event.type === "done") finalMessage = event.message;
        else if (event.type === "error") serverError = event.message;
        onEvent(event);
      } catch {
        /* 忽略非 JSON 心跳行 */
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    feed(decoder.decode(value, { stream: true }));
  }
  feed(decoder.decode());

  // 优先透出服务端给出的具体错误，避免被笼统文案覆盖。
  if (!finalMessage && serverError) throw new Error(serverError);
  if (!finalMessage) throw new Error("没有收到完整回复，请重试。");
  return finalMessage;
}
