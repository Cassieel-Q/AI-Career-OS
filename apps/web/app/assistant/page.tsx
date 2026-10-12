"use client";

import { useCallback, useEffect, useState } from "react";
import type { AssistantConversation } from "../assistant.ts";
import { createConversation, deleteConversation, listConversations } from "../assistant.ts";
import { readCurrentProfileId } from "../career-hub.ts";
import { AssistantChat } from "../assistant-chat.tsx";
import { readAssistantContext } from "../assistant-context.ts";

export default function AssistantPage() {
  const [conversations, setConversations] = useState<AssistantConversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  // 第三阶段：从岗位面试页进入时，URL 会带上 mission_id / target_resume_id，自动作为 Agent 上下文。
  const [missionId, setMissionId] = useState<string | null>(null);
  const [targetResumeId, setTargetResumeId] = useState<string | null>(null);
  const [route, setRoute] = useState<string | null>(null);
  const profileId = readCurrentProfileId();

  useEffect(() => {
    if (typeof window === "undefined") return;
    const context = readAssistantContext();
    setMissionId(context.missionId);
    setTargetResumeId(context.targetResumeId);
    setRoute(context.route);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const list = await listConversations("page");
      setConversations(list);
      if (!activeId && list.length) setActiveId(list[0].id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取会话失败。");
    } finally {
      setLoading(false);
    }
  }, [activeId]);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function newConversation() {
    setError("");
    try {
      const conv = await createConversation("page");
      setConversations((prev) => [conv, ...prev]);
      setActiveId(conv.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "新建会话失败。");
    }
  }

  async function remove(id: string) {
    if (!window.confirm("删除这段对话？")) return;
    setError("");
    try {
      await deleteConversation(id, "page");
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeId === id) setActiveId(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "删除失败。");
    }
  }

  function select(id: string) {
    // 历史消息由 AssistantChat 按 conversationId 自行回填，这里只切换选中项。
    setActiveId(id);
    setError("");
  }

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">顺顺 · AI Assistant</p>
          <h1 className="app-page-title">顺顺 · AI 求职助手</h1>
          <p className="app-page-subtitle">流式问答，可关联岗位 / 简历，按需联网搜索与写入。</p>
        </div>
        <button type="button" className="app-btn primary" onClick={() => void newConversation()}>
          新对话
        </button>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <div className="assistant-page-grid">
        <aside className="assistant-sidebar" aria-label="对话历史">
          <p className="assistant-sidebar-title">对话</p>
          {loading ? (
            <div className="app-empty">读取中…</div>
          ) : conversations.length ? (
            conversations.map((c) => (
              <div key={c.id} className={`assistant-sidebar-item${c.id === activeId ? " active" : ""}`}>
                <button type="button" className="assistant-sidebar-link" onClick={() => void select(c.id)}>
                  {c.title || "新对话"}
                </button>
                <button type="button" className="assistant-sidebar-del" aria-label="删除" title="删除" onClick={() => void remove(c.id)}>
                  ×
                </button>
              </div>
            ))
          ) : (
            <div className="app-empty">还没有对话。</div>
          )}
        </aside>

        <section className="assistant-main">
          {activeId || conversations.length === 0 ? (
            <AssistantChat
              surface="page"
              conversationId={activeId}
              profileId={profileId}
              missionId={missionId}
              targetResumeId={targetResumeId}
              route={route}
              onConversationChange={(id) => {
                setActiveId(id);
                void load();
              }}
            />
          ) : null}
        </section>
      </div>
    </main>
  );
}
