"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AssistantMessage, AssistantSurface, InterviewContextSummary } from "./assistant.ts";
import { createConversation, getConversation, resolveInterviewContext, streamChat } from "./assistant.ts";
import { Markdown } from "./markdown-render.tsx";

type Props = {
  surface: AssistantSurface;
  conversationId: string | null;
  profileId?: string | null;
  missionId?: string | null;
  /** 第三阶段：从岗位面试页进入时自动带上岗位版简历。 */
  targetResumeId?: string | null;
  route?: string | null;
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

const MISSING_LABELS: Record<string, string> = {
  mission: "岗位",
  target_resume: "岗位版简历",
  raw_jd: "JD 原文",
  raw_jd_from_message: "已使用本轮 JD",
  interview_intel: "真实面经",
};

/**
 * 工具名 → 用户可读的中文标签。
 * 后端工具名（list_jobs / get_job 等）是实现细节，不应直接暴露在对话气泡里。
 */
const TOOL_LABELS: Record<string, string> = {
  list_jobs: "查询岗位",
  get_job: "读取岗位详情",
  list_resumes: "查询简历",
  list_applications: "查询投递记录",
  list_interview_experiences: "查询面试记录",
  list_claims: "查询事实台账",
  list_reminders: "查询提醒",
  list_referrals: "查询内推记录",
  format_templates: "查询简历模板",
  diagnose_application_failure: "诊断投递问题",
  create_interview_experience: "记录面经",
  create_referral: "记录内推",
  create_reminder: "创建提醒",
  get_mission_context: "读取岗位上下文",
  get_target_resume_context: "读取岗位版简历",
  get_confirmed_claims_context: "读取已确认事实",
  get_interview_intel_context: "读取真实面经",
  web_search: "联网搜索",
};

function toolLabel(name: string): string {
  return TOOL_LABELS[name] ?? "查阅资料";
}

export function AssistantChat({
  surface,
  conversationId,
  profileId,
  missionId,
  targetResumeId,
  route,
  onConversationChange,
  compact = false,
}: Props) {
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [controls, setControls] = useState<Controls>(DEFAULT_CONTROLS);
  const [streamingText, setStreamingText] = useState("");
  const [activeTools, setActiveTools] = useState<Array<{ name: string; changed: boolean; summary: string }>>([]);
  const [activeSources, setActiveSources] = useState<Array<Record<string, unknown>>>([]);
  const [contextSummary, setContextSummary] = useState<InterviewContextSummary | null>(null);
  const [prepMode, setPrepMode] = useState<string | null>(null);
  const [degradedReasons, setDegradedReasons] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  // 记录已经回填过历史的会话，避免父组件重渲染时反复拉取、也避免覆盖正在发送的消息。
  const loadedConvRef = useRef<string | null>(null);

  // 切换会话时回填历史消息：之前从不加载，导致「不同对话点进去都是同一个 / 关掉就没了」。
  useEffect(() => {
    if (!conversationId) {
      loadedConvRef.current = null;
      setMessages([]);
      setStreamingText("");
      setActiveTools([]);
      return;
    }
    if (loadedConvRef.current === conversationId) return;
    loadedConvRef.current = conversationId;
    let cancelled = false;
    void (async () => {
      try {
        const detail = await getConversation(conversationId, surface);
        if (!cancelled) setMessages((detail.messages ?? []) as AssistantMessage[]);
      } catch {
        if (!cancelled) setMessages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, surface]);

  // 进入助手时自动解析面试上下文（岗位 / 简历版本 / 经历数 / 确认事实数 / 面经 / 缺失资料）。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await resolveInterviewContext({
          profile_id: profileId ?? null,
          mission_id: missionId ?? null,
          target_resume_id: targetResumeId ?? null,
          route,
        });
        if (cancelled) return;
        setContextSummary(result.summary ?? null);
        setPrepMode(result.prep?.mode ?? null);
      } catch {
        if (!cancelled) setContextSummary(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [profileId, missionId, targetResumeId, route]);

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
    try {
      if (!cid) {
        const conv = await createConversation(surface);
        cid = conv.id;
        // 新会话刚创建，标记为已加载，避免下面的回填 effect 把刚发出的消息清空。
        loadedConvRef.current = conv.id;
        onConversationChange?.(conv.id);
      }
    } catch {
      // 之前这步在 try 之外，创建会话失败会变成裸 "network error"。
      setError("连接本地服务失败。请确认 AI Career OS 后端已启动，然后重试。");
      return;
    }
    const userMessage: AssistantMessage = { id: `local-${Date.now()}`, role: "user", content };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setBusy(true);
    setError("");
    setStreamingText("");
    setActiveTools([]);
    setActiveSources([]);
    setDegradedReasons([]);

    let fullText = "";
    try {
      const finalMessage = await streamChat(
        cid,
        {
          content,
          profile_id: profileId ?? null,
          mission_id: missionId ?? null,
          target_resume_id: targetResumeId ?? null,
          route: route ?? null,
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
          else if (event.type === "degraded") setDegradedReasons(event.reasons);
          else if (event.type === "error") setError(event.message);
        },
      );
      // 以服务端落库的最终消息为准（避免与流式片段不一致）。
      const finalText = (finalMessage.content || fullText || "（已处理）").trim();
      setMessages((prev) => [
        ...prev,
        { id: finalMessage.id || `local-${Date.now()}-a`, role: "assistant", content: finalText, tool_calls: finalMessage.tool_calls ?? null, sources: finalMessage.sources ?? null },
      ]);
      setStreamingText("");
      setActiveTools([]);
    } catch (caught) {
      const raw = caught instanceof Error ? caught.message : "";
      // fetch 层失败（连接中断/后端未启动）浏览器只给英文 "network error"，换成可操作的中文。
      const message = /network|failed to fetch|load failed/i.test(raw)
        ? "与本地服务的连接中断了。请确认后端已启动后重试；如果反复出现，重启 AI Career OS 再试。"
        : caught instanceof Error ? caught.message : "发送失败。";
      // 保留已经流出的部分内容，避免"答到一半"的成果被清空。
      if (fullText.trim()) {
        setMessages((prev) => [...prev, { id: `local-${Date.now()}-partial`, role: "assistant", content: fullText.trim() }]);
      }
      setError(message);
      setStreamingText("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="assistant-chat">
      {contextSummary ? (
        <div className="assistant-context" role="status" aria-label="当前 Agent 上下文">
          <span className="assistant-context-title">当前上下文</span>
          <span className="assistant-context-item">
            岗位：{contextSummary.company || "未识别"} · {contextSummary.role || "未识别"}
          </span>
          <span className="assistant-context-item">
            简历版本：{contextSummary.resume_version != null ? `v${contextSummary.resume_version}（${contextSummary.resume_status || "DRAFT"}）` : "未绑定岗位版简历"}
          </span>
          <span className="assistant-context-item">已加载经历：{contextSummary.experience_count}</span>
          <span className="assistant-context-item">已确认事实：{contextSummary.confirmed_claims_count}</span>
          <span className="assistant-context-item">面经：{contextSummary.has_interview_intel ? "有" : "无"}</span>
          {prepMode === "CRASH_PREP" ? <span className="assistant-context-flag">短时准备模式</span> : null}
          {contextSummary.missing_context.length ? (
            <span className="assistant-context-missing">
              缺失资料：{contextSummary.missing_context.map((item) => MISSING_LABELS[item] || item).join("、")}
            </span>
          ) : null}
        </div>
      ) : null}

      {degradedReasons.length ? (
        <p className="assistant-degraded" role="alert">
          ⚠️ 部分资料本次未加载成功（{degradedReasons.join("；")}）。回答基于已成功加载的内容。
        </p>
      ) : null}

      <div className="assistant-messages" ref={scrollRef}>
        {messages.length === 0 && !streamingText ? (
          <div className="assistant-empty">
            <p className="assistant-empty-title">你好，我是「顺顺」</p>
            <p>可以问我岗位怎么准备、简历怎么改、投递卡在哪、面经怎么沉淀。涉及你的数据我会先查证再回答。</p>
          </div>
        ) : null}

        {messages.map((m) => (
          <div key={m.id} className={`assistant-msg ${m.role}`}>
            <div className="assistant-msg-body">
              <span className="assistant-msg-role">{m.role === "user" ? "你" : "顺顺"}</span>
              {m.role === "user" ? (
                <p className="assistant-msg-text">{m.content}</p>
              ) : (
                <div className="assistant-msg-text">
                  <Markdown text={m.content} />
                </div>
              )}
              {m.tool_calls && m.tool_calls.length > 0 ? (
                <div className="assistant-tools">
                  {m.tool_calls.map((t, i) => (
                    <span key={i} className="assistant-tool-chip" title={t.summary}>
                      {t.changed ? "✓" : "○"} {toolLabel(t.name)}
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
              <span className="assistant-msg-role">顺顺</span>
              <div className="assistant-msg-text assistant-streaming">
                <Markdown text={streamingText} />
                <span className="assistant-caret" />
              </div>
            </div>
          </div>
        ) : null}

        {activeTools.length > 0 && !streamingText ? (
          <div className="assistant-msg assistant">
            <div className="assistant-msg-body">
              <span className="assistant-msg-role">顺顺</span>
              <div className="assistant-tools">
                {activeTools.map((t, i) => (
                  <span key={i} className="assistant-tool-chip" title={t.summary}>
                    {t.changed ? "✓" : "○"} {toolLabel(t.name)}
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
