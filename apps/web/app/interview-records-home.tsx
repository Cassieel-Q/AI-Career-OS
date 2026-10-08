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
import { listProfileLabelOptions } from "./profile-label.ts";

export function InterviewRecordsHome() {
  const [profileId, setProfileId] = useState("");
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
    const initial = readStoredProfileId();
    const options = listProfileLabelOptions();
    const fallback = initial || options[0]?.profileId || "";
    setProfileId(fallback);
    if (fallback) void load(fallback);
  }, [load]);

  const profiles = listProfileLabelOptions();

  return (
    <main className="mission-home">
      <header className="workflow-header">
        <Link className="workflow-brand" href="/missions">
          <span className="workflow-brand-mark" aria-hidden="true">
            A
          </span>
          <span>AI Career OS</span>
        </Link>
      </header>
      <section className="mission-home-content">
        <p className="eyebrow">面试记录库</p>
        <h1>按公司归档的真实面试</h1>
        <p className="summary">把一面 / 二面 / 三面的题目和回答留下来，录入后可走评分、复盘和补强建议。</p>

        <div className="mission-home-actions">
          <Link className="mission-primary-cta link-cta" href={"/interview-records/new" as Route}>
            新建录入
          </Link>
          <Link className="button-secondary" href={"/missions" as Route}>
            返回岗位准备
          </Link>
        </div>

        <div className="mission-profile-form">
          <label className="field-label">
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
            <p className="profile-note">
              本机还没有档案。请先回首页上传简历，或从岗位准备页恢复档案 ID。
            </p>
          ) : null}
        </div>

        {error ? (
          <p className="message error" role="alert">
            {error}
          </p>
        ) : null}
        {loading ? (
          <p className="profile-note" role="status">
            读取中…
          </p>
        ) : null}

        <section className="mission-list" aria-label="按公司分组的面试记录">
          {companies.length ? (
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
            <div className="mission-empty">还没有面试记录。点击「新建录入」开始第一场。</div>
          )}
        </section>
      </section>
    </main>
  );
}
