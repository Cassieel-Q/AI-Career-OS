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
  web_search: boolean;
  allow_write: boolean;
  reasoning_effort: "low" | "medium" | "high";
};

export type StreamEvent =
  | { type: "start"; conversation_id: string }
  | { type: "delta"; text: string }
  | { type: "tool"; name: string; changed: boolean; summary: string }
  | { type: "sources"; sources: Array<Record<string, unknown>> }
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
