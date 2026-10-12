"use client";

/**
 * 岗位匹配分析侧栏（用户诉求：「点一下岗位名称，右边拉出半边侧栏，
 * 说明为什么匹配 / 哪里不匹配 / 是否值得投递；再点一下进入正常岗位页面」）。
 *
 * - 打开即拉一次明细（命中后端缓存，不会重复调模型）；
 * - 「重新分析」才 POST 触发模型重算；
 * - 侧栏底部与标题都可进入岗位页面。
 */
import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import { ScoreRing } from "./score-ring.tsx";
import {
  fetchJobKeywords,
  fetchJobMatch,
  refreshJobKeywords,
  refreshJobMatch,
  sourceLabel,
  verdictLabel,
  verdictTone,
  type JobKeywordAnalysis,
  type JobMatchAnalysis,
} from "./job-insight.ts";
import { isUnknownIdentity } from "./mission-state.ts";

type Props = {
  missionId: string;
  role: string;
  company: string;
  location?: string | null;
  seniority?: string;
  href: Route;
  onClose: () => void;
};

export function JobMatchDrawer({ missionId, role, company, location, seniority, href, onClose }: Props) {
  const [match, setMatch] = useState<JobMatchAnalysis | null>(null);
  const [keywords, setKeywords] = useState<JobKeywordAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextMatch, nextKeywords] = await Promise.all([
        fetchJobMatch(missionId),
        fetchJobKeywords(missionId),
      ]);
      setMatch(nextMatch);
      setKeywords(nextKeywords);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取匹配分析失败。");
    } finally {
      setLoading(false);
    }
  }, [missionId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function reanalyze() {
    setBusy(true);
    setError("");
    try {
      const [nextMatch, nextKeywords] = await Promise.all([
        refreshJobMatch(missionId),
        refreshJobKeywords(missionId),
      ]);
      setMatch(nextMatch);
      setKeywords(nextKeywords);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "重新分析失败。");
    } finally {
      setBusy(false);
    }
  }

  const roleLabel = isUnknownIdentity(role) ? "未命名岗位" : role;
  const companyLabel = isUnknownIdentity(company) ? "" : company;
  const tone = verdictTone(match?.verdict);
  const toneClass = tone === "good" ? "filled" : tone === "warn" ? "attention" : tone === "bad" ? "danger" : "muted";

  return (
    <aside className="toutou-drawer job-drawer" role="dialog" aria-label="岗位匹配分析">
      <div className="toutou-drawer-head">
        <div>
          <span className="toutou-dot" aria-hidden="true" />
          <strong>岗位匹配分析</strong>
        </div>
        <button type="button" className="toutou-close" onClick={onClose} aria-label="关闭">
          ×
        </button>
      </div>

      <div className="toutou-drawer-body job-drawer-body">
        <div className="job-drawer-title">
          <Link href={href} className="job-drawer-name" title="点一下进入岗位页面">
            {roleLabel}
          </Link>
          <p className="job-drawer-meta">
            {[companyLabel, location, seniority && seniority !== "UNKNOWN" ? seniority : ""]
              .filter(Boolean)
              .join(" · ") || "—"}
          </p>
          {keywords?.keywords?.length ? (
            <div className="kw-chips">
              {keywords.keywords.map((word) => (
                <span key={word} className="kw-chip">{word}</span>
              ))}
            </div>
          ) : null}
        </div>

        {error ? <p className="message error" role="alert">{error}</p> : null}

        {loading ? (
          <div className="app-empty">正在读取匹配分析…</div>
        ) : match ? (
          <>
            <section className="job-drawer-score">
              <ScoreRing score={match.score} size={88} large />
              <div>
                <span className={`app-badge ${toneClass}`}>
                  {verdictLabel(match.verdict, match.verdict_label)}
                </span>
                <p className="job-drawer-advice">{match.advice || "暂无建议。"}</p>
              </div>
            </section>

            <section className="job-drawer-block">
              <h4>为什么匹配</h4>
              {match.reasons.length ? (
                <ul className="job-drawer-list good">
                  {match.reasons.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="summary">暂时没有找到可直接对应的简历依据。</p>
              )}
            </section>

            <section className="job-drawer-block">
              <h4>哪里不匹配</h4>
              {match.gaps.length ? (
                <ul className="job-drawer-list bad">
                  {match.gaps.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="summary">没有发现明显缺口。</p>
              )}
            </section>

            <section className="job-drawer-block">
              <h4>是否值得投递</h4>
              <p className="summary">
                {verdictLabel(match.verdict, match.verdict_label)}：{match.advice || "先补齐缺口再投。"}
              </p>
              <p className="job-drawer-source">
                {sourceLabel(match.source)}
                {match.resume_source === "MISSING" ? " · 尚未绑定简历" : ""}
                {match.resume_source === "EDITED_TEXT" ? " · 依据简历工作台原文" : ""}
                {match.resume_source === "PROFILE_FACTS" ? " · 依据已确认简历事实" : ""}
              </p>
            </section>
          </>
        ) : null}
      </div>

      <div className="job-drawer-foot">
        <button type="button" className="app-btn" disabled={busy} onClick={() => void reanalyze()}>
          {busy ? "分析中…" : "重新分析"}
        </button>
        <Link className="app-btn primary" href={href}>进入岗位页面</Link>
      </div>
    </aside>
  );
}

export default JobMatchDrawer;
