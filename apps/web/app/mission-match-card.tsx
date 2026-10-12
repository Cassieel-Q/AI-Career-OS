"use client";

/**
 * 岗位页面上的「简历匹配度」卡片。
 *
 * 用户诉求：「岗位页也要有评分和为什么匹配，评分用圆环」。
 * 数据来源与列表页侧栏一致（`/job-missions/{id}/match-analysis`），命中后端缓存。
 */
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

type Props = {
  missionId: string;
};

export function MissionMatchCard({ missionId }: Props) {
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
      setError(caught instanceof Error ? caught.message : "读取匹配度失败。");
    } finally {
      setLoading(false);
    }
  }, [missionId]);

  useEffect(() => {
    void load();
  }, [load]);

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

  if (loading) {
    return (
      <section className="mission-card" role="status">
        <p className="section-kicker">简历匹配度</p>
        <p className="summary">正在按你的简历分析这个岗位…</p>
      </section>
    );
  }

  const tone = verdictTone(match?.verdict);
  const toneClass = tone === "good" ? "filled" : tone === "warn" ? "attention" : tone === "bad" ? "danger" : "muted";

  return (
    <section className="mission-card mission-match-card">
      <p className="section-kicker">简历匹配度</p>
      <div className="mission-match-head">
        <ScoreRing score={match?.score ?? null} size={88} large />
        <div className="mission-match-head-text">
          <span className={`app-badge ${toneClass}`}>
            {verdictLabel(match?.verdict, match?.verdict_label ?? "待评估")}
          </span>
          {keywords?.keywords?.length ? (
            <div className="kw-chips">
              {keywords.keywords.map((word) => (
                <span key={word} className="kw-chip">{word}</span>
              ))}
            </div>
          ) : null}
        </div>
      </div>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      {match ? (
        <>
          <section className="mission-match-block">
            <h4>是否值得投递</h4>
            <p className="summary">
              {verdictLabel(match.verdict, match.verdict_label)}：{match.advice || "先补齐缺口再投。"}
            </p>
          </section>
          <div className="mission-match-grid">
            <div>
              <h4>为什么匹配</h4>
              {match.reasons.length ? (
                <ul className="job-drawer-list good">
                  {match.reasons.map((item) => <li key={item}>{item}</li>)}
                </ul>
              ) : (
                <p className="summary">暂时没有找到可直接对应的简历依据。</p>
              )}
            </div>
            <div>
              <h4>哪里不匹配</h4>
              {match.gaps.length ? (
                <ul className="job-drawer-list bad">
                  {match.gaps.map((item) => <li key={item}>{item}</li>)}
                </ul>
              ) : (
                <p className="summary">没有发现明显缺口。</p>
              )}
            </div>
          </div>
        </>
      ) : null}

      <div className="mission-action-row mission-action-wrap">
        <button type="button" className="app-btn" disabled={busy} onClick={() => void reanalyze()}>
          {busy ? "分析中…" : "重新分析"}
        </button>
        {match ? (
          <span className="job-drawer-source">
            {sourceLabel(match.source)}
            {match.resume_source === "MISSING" ? " · 尚未绑定简历" : ""}
            {match.resume_source === "EDITED_TEXT" ? " · 依据简历工作台原文" : ""}
            {match.resume_source === "PROFILE_FACTS" ? " · 依据已确认简历事实" : ""}
          </span>
        ) : null}
      </div>
    </section>
  );
}

export default MissionMatchCard;
