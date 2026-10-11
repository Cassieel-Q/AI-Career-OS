"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import {
  listInterviewRecords,
  readStoredProfileId,
  type InterviewRecordCompanyGroup,
  PROFILE_STORAGE_KEY,
} from "./interview-records.ts";
import { listProfileLabelOptions, type ProfileOptionView } from "./profile-label.ts";

export function InterviewRecordsHome() {
  const [profileId, setProfileId] = useState("");
  const [profiles, setProfiles] = useState<ProfileOptionView[]>([]);
  const [companies, setCompanies] = useState<InterviewRecordCompanyGroup[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (id: string) => {
    const normalized = id.trim();
    if (!normalized) {
      setCompanies([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      window.localStorage.setItem(PROFILE_STORAGE_KEY, normalized);
      const data = await listInterviewRecords(normalized);
      setCompanies(data.companies || []);
    } catch (caught) {
      setCompanies([]);
      setError(caught instanceof Error ? caught.message : "读取面试记录失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const options = listProfileLabelOptions();
    setProfiles(options);
    const initial = readStoredProfileId();
    const fallback = initial || options[0]?.profileId || "";
    setProfileId(fallback);
    if (fallback) void load(fallback);
  }, [load]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Interviews</p>
          <h1 className="app-page-title">面试</h1>
          <p className="app-page-subtitle">把一面 / 二面 / 三面的题目和回答留下来，录入后可走评分、复盘和补强建议。</p>
        </div>
        <Link className="app-btn primary" href={"/interview-records/new" as Route}>
          新建录入
        </Link>
      </header>

      <div className="app-filter-row" aria-label="选择档案">
        <label className="field-label" style={{ display: "grid", gap: "0.35rem", minWidth: "16rem" }}>
          选择档案
          <select
            value={profileId}
            disabled={loading}
            aria-label="选择档案"
            onChange={(event) => {
              const next = event.target.value;
              setProfileId(next);
              void load(next);
            }}
          >
            <option value="">请选择档案</option>
            {profiles.map((profile) => (
              <option key={profile.profileId} value={profile.profileId}>
                {profile.displayLabel || profile.label || "未命名档案"}
              </option>
            ))}
          </select>
        </label>
        {!profiles.length ? (
          <p className="app-card-meta" style={{ alignSelf: "end", paddingBottom: "0.4rem" }}>
            本机还没有档案。请先回首页上传简历。
          </p>
        ) : null}
      </div>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <section className="mission-list" aria-label="按公司分组的面试记录" style={{ marginTop: "1rem" }}>
        {loading ? (
          <div className="app-empty">读取中…</div>
        ) : companies.length ? (
          companies.map((group) => (
            <article className="mission-list-card" key={group.company_key}>
              <Link
                className="mission-list-card-main"
                href={`/interview-records/company/${group.company_key}` as Route}
              >
                <div>
                  <p className="section-kicker">文件夹</p>
                  <h2>{group.company}</h2>
                  <p>
                    {group.record_count} 场
                    {group.latest_interviewed_on ? ` · 最近 ${group.latest_interviewed_on}` : ""}
                    {group.rounds.length ? ` · ${group.rounds.join(" / ")}` : ""}
                  </p>
                </div>
                <span className="mission-status-badge">打开</span>
              </Link>
            </article>
          ))
        ) : (
          <div className="app-empty">还没有面试记录。点击「新建录入」开始第一场。</div>
        )}
      </section>
    </main>
  );
}
