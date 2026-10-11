"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  INTERVIEW_ROUNDS,
  companyNameFromKey,
  listInterviewRecords,
  readStoredProfileId,
  type InterviewRecord,
  PROFILE_STORAGE_KEY,
} from "./interview-records.ts";

export function InterviewRecordsCompany({ companyKey }: { companyKey: string }) {
  const company = companyNameFromKey(companyKey);
  const [profileId, setProfileId] = useState("");
  const [records, setRecords] = useState<InterviewRecord[]>([]);
  const [roundFilter, setRoundFilter] = useState("全部");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async (id: string) => {
    const normalized = id.trim();
    if (!normalized) {
      setRecords([]);
      return;
    }
    setLoading(true);
    setError("");
    try {
      window.localStorage.setItem(PROFILE_STORAGE_KEY, normalized);
      const data = await listInterviewRecords(normalized);
      const group = (data.companies || []).find((item) => item.company === company);
      setRecords(group?.records || []);
    } catch (caught) {
      setRecords([]);
      setError(caught instanceof Error ? caught.message : "读取公司面试记录失败");
    } finally {
      setLoading(false);
    }
  }, [company]);

  useEffect(() => {
    const initial = readStoredProfileId();
    setProfileId(initial);
    if (initial) void load(initial);
  }, [load]);

  const filtered = useMemo(() => {
    if (roundFilter === "全部") return records;
    return records.filter((item) => item.interview_round === roundFilter);
  }, [records, roundFilter]);

  return (
    <main className="mission-home">
      <section className="mission-home-content">
        <p style={{ margin: 0 }}>
          <Link className="button-secondary" href={"/interview-records" as Route}>← 返回面试</Link>
        </p>
        <p className="eyebrow">公司文件夹</p>
        <h1>{company || "未命名公司"}</h1>
        <p className="summary">同公司不同面次放在一起。可用下拉筛选一面 / 二面 / 三面。</p>

        <div className="mission-home-actions">
          <Link
            className="mission-primary-cta link-cta"
            href={`/interview-records/new?company=${encodeURIComponent(company)}` as Route}
          >
            为本公司新建录入
          </Link>
        </div>

        <div className="mission-profile-form">
          <label className="field-label">
            轮次筛选
            <select
              value={roundFilter}
              aria-label="轮次筛选"
              onChange={(event) => setRoundFilter(event.target.value)}
            >
              <option value="全部">全部</option>
              {INTERVIEW_ROUNDS.map((round) => (
                <option key={round} value={round}>
                  {round}
                </option>
              ))}
            </select>
          </label>
        </div>

        {!profileId ? (
          <p className="message error">请先在首页选择档案，再打开公司文件夹。</p>
        ) : null}
        {error ? (
          <p className="message error" role="alert">
            {error}
          </p>
        ) : null}
        {loading ? <p className="profile-note">读取中…</p> : null}

        <section className="mission-list" aria-label={`${company} 的面试记录`}>
          {filtered.length ? (
            filtered.map((record) => (
              <article className="mission-list-card" key={record.id}>
                <Link
                  className="mission-list-card-main"
                  href={`/interview-records/${encodeURIComponent(record.id)}` as Route}
                >
                  <div>
                    <p className="section-kicker">{record.interviewed_on}</p>
                    <h2>
                      {record.interview_round}
                      {record.role ? ` · ${record.role}` : ""}
                    </h2>
                    <p>{record.items?.length || 0} 道题</p>
                  </div>
                  <span className="mission-status-badge">
                    {record.evaluated || record.status === "EVALUATED" ? "已评分" : "未评分"}
                  </span>
                </Link>
              </article>
            ))
          ) : (
            <div className="mission-empty">这个筛选下还没有记录。</div>
          )}
        </section>
      </section>
    </main>
  );
}
