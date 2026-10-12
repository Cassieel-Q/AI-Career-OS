"use client";

import { useEffect, useState } from "react";
import { AssistantChat } from "./assistant-chat.tsx";
import { listConversations, type AssistantConversation } from "./assistant.ts";
import { readCurrentProfileId } from "./career-hub.ts";
import { missionIdFromPath, readAssistantContext } from "./assistant-context.ts";

/**
 * 「顺顺」悬浮球：任意页面右下角常驻，点击打开浮窗问答。
 * 浮窗只展示联网搜索 + 思考强度两个控制；记录与侧栏助手页分开保存（surface=orb）。
 */
export function TouTouOrb() {
  const [open, setOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [missionId, setMissionId] = useState<string | null>(null);
  const [targetResumeId, setTargetResumeId] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    if (typeof window !== "undefined") {
      // 第三阶段：浮窗也自动带上下文（URL 兜底从 /missions/<id> 解析）。
      const context = readAssistantContext();
      setMissionId(context.missionId || missionIdFromPath(window.location.pathname));
      setTargetResumeId(context.targetResumeId);
    }
    let active = true;
    listConversations("orb")
      .then((list) => {
        if (!active) return;
        // 复用最近一次浮窗会话；没有就新建。
        setConversationId(list.length ? list[0].id : null);
      })
      .catch(() => setConversationId(null));
    return () => {
      active = false;
    };
  }, [open]);

  const profileId = readCurrentProfileId();

  return (
    <>
      {open ? (
        <div className="toutou-drawer" role="dialog" aria-label="顺顺助手浮窗">
          <div className="toutou-drawer-head">
            <div>
              <span className="toutou-dot" aria-hidden="true" />
              <strong>顺顺</strong>
            </div>
            <button type="button" className="toutou-close" onClick={() => setOpen(false)} aria-label="关闭">
              ×
            </button>
          </div>
          <div className="toutou-drawer-body">
            <AssistantChat
              surface="orb"
              conversationId={conversationId}
              profileId={profileId}
              missionId={missionId}
              targetResumeId={targetResumeId}
              compact
              onConversationChange={(id) => setConversationId(id)}
            />
          </div>
        </div>
      ) : null}

      <button
        type="button"
        className={`toutou-orb${open ? " open" : ""}`}
        onClick={() => setOpen((v) => !v)}
        aria-label="打开顺顺助手"
        title="顺顺 · AI 求职助手"
      >
        {open ? (
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 6h16v10.5h-6l-4 4v-4H4z" />
            <circle cx="9" cy="11" r="1" fill="currentColor" />
            <circle cx="12" cy="11" r="1" fill="currentColor" />
            <circle cx="15" cy="11" r="1" fill="currentColor" />
          </svg>
        )}
      </button>
    </>
  );
}
