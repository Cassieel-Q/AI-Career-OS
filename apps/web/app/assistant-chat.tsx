"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AssistantMessage, AssistantSurface } from "./assistant.ts";
import { createConversation, streamChat } from "./assistant.ts";

type Props = {
  surface: AssistantSurface;
  conversationId: string | null;
  profileId?: string | null;
  missionId?: string | null;
  /** 会话列表变动时通知外层（用于刷新侧栏） */
  onConversationChange?: (id: string) => void;
  /** 浮窗模式只展示联网与思考强度，不展示「允许写入」开关 */
  compact?: boolean;
};

type Controls = {
  web_search: boolean;
  allow_write: boolean;
  reasoning_effort: "low" | "medium" | "high";
};

const DEFAULT_CONTROLS: Controls = { web_search: false, allow_write: true, reasoning_effort: "medium" };

export function AssistantChat({ surface, conversationId, profileId, missionId, onConversationChange, compact = false }: Props) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [controls, setControls] = useState<Controls>(DEFAULT_CONTROLS);
  const [streamingText, setStreamingText] = useState("");
  const [activeTools, setActiveTools] = useState<Array<{ name: string; changed: boolean; summary: string }>>([]);
  const [activeSources, setActiveSources] = useState<Array<Record<string, unknown>>>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingText, scrollToBottom]);

  async function send() {
    const content = input.trim();
    if (!content || busy) return;
    let cid = conversationId;
    if (!cid) {
      const conv = await createConversation(surface);
      cid = conv.id;
      onConversationChange?.(conv.id);
    }
    const userMessage: AssistantMessage = { id: `local-${Date.now()}`, role: "user", content };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setBusy(true);
    setError("");
    setStreamingText("");
    setActiveTools([]);
    setActiveSources([]);

    let fullText = "";
    try {
      await streamChat(
        cid,
        {
          content,
          profile_id: profileId ?? null,
          mission_id: missionId ?? null,
          web_search: controls.web_search,
          allow_write: controls.allow_write,
          reasoning_effort: controls.reasoning_effort,
        },
        (event) => {
          if (event.type === "delta") {
            fullText += event.text;
            setStreamingText(fullText);
          } else if (event.type === "tool") setActiveTools((prev) => [...prev, { name: event.name, changed: event.changed, summary: event.summary }]);
          else if (event.type === "sources") setActiveSources(event.sources as Array<Record<string, unknown>>);
          else if (event.type === "error") setError(event.message);
        },
      );
      // 追加助手消息
      setMessages((prev) => {
        const final: AssistantMessage = { id: `local-${Date.now()}-a`, role: "assistant", content: fullText || "（已处理）" };
        return [...prev, final];
      });
      setStreamingText("");
      setActiveTools([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "发送失败。");
      setStreamingText("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="assistant-chat">
      <div className="assistant-messages" ref={scrollRef}>
        {messages.length === 0 && !streamingText ? (
          <div className="assistant-empty">
            <p className="assistant-empty-title">你好，我是「投投」</p>
            <p>可以问我岗位怎么准备、简历怎么改、投递卡在哪、面经怎么沉淀。涉及你的数据我会先查证再回答。</p>
          </div>
        ) : null}

        {messages.map((m) => (
          <div key={m.id} className={`assistant-msg ${m.role}`}>
            <div className="assistant-msg-body">
              <span className="assistant-msg-role">{m.role === "user" ? "你" : "投投"}</span>
              <p className="assistant-msg-text">{m.content}</p>
              {m.tool_calls && m.tool_calls.length > 0 ? (
                <div className="assistant-tools">
                  {m.tool_calls.map((t, i) => (
                    <span key={i} className="assistant-tool-chip" title={t.summary}>
                      {t.changed ? "✓" : "○"} {t.name}
                    </span>
                  ))}
                </div>
              ) : null}
              {m.sources && m.sources.length > 0 ? <SourceList sources={m.sources as Array<Record<string, unknown>>} /> : null}
            </div>
          </div>
        ))}

        {streamingText ? (
          <div className="assistant-msg assistant">
            <div className="assistant-msg-body">
              <span className="assistant-msg-role">投投</span>
              <p className="assistant-msg-text assistant-streaming">{streamingText}<span className="assistant-caret" /></p>
            </div>
          </div>
        ) : null}

        {activeTools.length > 0 && !streamingText ? (
          <div className="assistant-msg assistant">
            <div className="assistant-msg-body">
              <span className="assistant-msg-role">投投</span>
              <div className="assistant-tools">
                {activeTools.map((t, i) => (
                  <span key={i} className="assistant-tool-chip" title={t.summary}>
                    {t.changed ? "✓" : "○"} {t.name}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>

      {error ? <p className="assistant-error" role="alert">{error}</p> : null}

      <div className="assistant-controls">
        <label className="assistant-toggle">
          <input type="checkbox" checked={controls.web_search} onChange={(e) => setControls({ ...controls, web_search: e.target.checked })} />
          联网搜索
        </label>
        {!compact ? (
          <label className="assistant-toggle">
            <input type="checkbox" checked={controls.allow_write} onChange={(e) => setControls({ ...controls, allow_write: e.target.checked })} />
            允许写入
          </label>
        ) : null}
        <label className="assistant-effort">
          思考强度
          <select value={controls.reasoning_effort} onChange={(e) => setControls({ ...controls, reasoning_effort: e.target.value as Controls["reasoning_effort"] })}>
            <option value="low">简洁</option>
            <option value="medium">适中</option>
            <option value="high">深入</option>
          </select>
        </label>
      </div>

      <div className="assistant-input-row">
        <textarea
          className="assistant-input"
          value={input}
          placeholder="问点求职相关的事…（Enter 发送，Shift+Enter 换行）"
          rows={2}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button type="button" className="app-btn primary" disabled={busy || !input.trim()} onClick={() => void send()}>
          {busy ? "思考中…" : "发送"}
        </button>
      </div>
    </div>
  );
}

function SourceList({ sources }: { sources: Array<Record<string, unknown>> }) {
  if (sources.length === 1 && sources[0].error) {
    return <p className="assistant-sources-note">{String(sources[0].error)}</p>;
  }
  return (
    <div className="assistant-sources">
      <span className="assistant-sources-label">参考来源</span>
      {sources.map((s, i) => (
        <a key={i} className="assistant-source" href={String(s.url || "#")} target="_blank" rel="noreferrer">
          [{i + 1}] {String(s.title || s.url || "")}
        </a>
      ))}
    </div>
  );
}
