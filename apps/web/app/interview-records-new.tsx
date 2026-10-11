"use client";

import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import {
  INTERVIEW_ROUNDS,
  createInterviewRecord,
  evaluateInterviewRecord,
  readStoredProfileId,
  type InterviewRound,
  PROFILE_STORAGE_KEY,
} from "./interview-records.ts";
import { listProfileLabelOptions } from "./profile-label.ts";

type DraftItem = { question: string; context: string; my_answer: string };

function todayIso(): string {
  const now = new Date();
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function InterviewRecordsNew({ initialCompany = "" }: { initialCompany?: string }) {
  const router = useRouter();
  const [profileId, setProfileId] = useState("");
  const [company, setCompany] = useState(initialCompany);
  const [role, setRole] = useState("");
  const [interviewedOn, setInterviewedOn] = useState(todayIso());
  const [round, setRound] = useState<InterviewRound>("一面");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<DraftItem[]>([{ question: "", context: "", my_answer: "" }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const initial = readStoredProfileId() || listProfileLabelOptions()[0]?.profileId || "";
    setProfileId(initial);
  }, []);

  const profiles = useMemo(() => listProfileLabelOptions(), []);

  function updateItem(index: number, patch: Partial<DraftItem>) {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    const pid = profileId.trim();
    if (!pid) {
      setError("请先选择档案");
      return;
    }
    if (!company.trim()) {
      setError("请填写公司");
      return;
    }
    if (!interviewedOn) {
      setError("请填写面试日期");
      return;
    }
    const cleaned = items
      .map((item, index) => ({
        question: item.question.trim(),
        context: item.context.trim() || null,
        my_answer: item.my_answer.trim(),
        sort_order: index,
      }))
      .filter((item) => item.question && item.my_answer);
    if (!cleaned.length) {
      setError("请至少录入一道完整的问题与回答");
      return;
    }
    setBusy(true);
    setError("");
    try {
      window.localStorage.setItem(PROFILE_STORAGE_KEY, pid);
      const created = await createInterviewRecord(pid, {
        company: company.trim(),
        role: role.trim() || null,
        interview_round: round,
        interviewed_on: interviewedOn,
        notes: notes.trim() || null,
        items: cleaned,
      });
      try {
        await evaluateInterviewRecord(created.id);
      } catch (evalError) {
        // Still jump to detail; detail page can show unevaluated + retry.
        console.warn("evaluate failed", evalError);
        setError(evalError instanceof Error ? `已保存，但评分失败：${evalError.message}` : "已保存，但评分失败");
        router.push(`/interview-records/${encodeURIComponent(created.id)}` as Route);
        return;
      }
      router.push(`/interview-records/${encodeURIComponent(created.id)}` as Route);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "录入失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mission-home">
      <section className="mission-home-content">
        <p style={{ margin: 0 }}>
          <Link className="button-secondary" href={"/interview-records" as Route}>← 返回面试</Link>
        </p>
        <p className="eyebrow">新建录入</p>
        <h1>记录一场真实面试</h1>
        <p className="summary">填写公司、轮次和问答。保存后会自动评分并生成复盘 / 补强建议。</p>

        <form className="mission-card mission-form" onSubmit={(event) => void onSubmit(event)}>
          <label className="field-label">
            档案
            <select
              value={profileId}
              required
              onChange={(event) => setProfileId(event.target.value)}
              aria-label="选择档案"
            >
              <option value="">请选择档案</option>
              {profiles.map((profile) => (
                <option key={profile.profileId} value={profile.profileId}>
                  {profile.displayLabel || profile.label || "未命名档案"}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label">
            公司（必填）
            <input className="text-input" value={company} required onChange={(e) => setCompany(e.target.value)} />
          </label>
          <label className="field-label">
            岗位 / 角色（可选）
            <input className="text-input" value={role} onChange={(e) => setRole(e.target.value)} />
          </label>
          <label className="field-label">
            面试日期（必填）
            <input
              className="text-input"
              type="date"
              value={interviewedOn}
              required
              onChange={(e) => setInterviewedOn(e.target.value)}
            />
          </label>
          <label className="field-label">
            轮次
            <select value={round} onChange={(e) => setRound(e.target.value as InterviewRound)}>
              {INTERVIEW_ROUNDS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="field-label">
            备注（可选）
            <textarea className="textarea" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>

          <div className="proof-card-list">
            {items.map((item, index) => (
              <div className="proof-card" key={`item-${index}`}>
                <h3>问答 {index + 1}</h3>
                <label className="field-label">
                  问题
                  <textarea
                    className="textarea"
                    rows={2}
                    value={item.question}
                    onChange={(e) => updateItem(index, { question: e.target.value })}
                  />
                </label>
                <label className="field-label">
                  内容 / 上下文（可选）
                  <textarea
                    className="textarea"
                    rows={2}
                    value={item.context}
                    onChange={(e) => updateItem(index, { context: e.target.value })}
                  />
                </label>
                <label className="field-label">
                  我的回答
                  <textarea
                    className="textarea"
                    rows={4}
                    value={item.my_answer}
                    onChange={(e) => updateItem(index, { my_answer: e.target.value })}
                  />
                </label>
                {items.length > 1 ? (
                  <button
                    type="button"
                    className="button-secondary"
                    onClick={() => setItems((prev) => prev.filter((_, i) => i !== index))}
                  >
                    删除这道题
                  </button>
                ) : null}
              </div>
            ))}
          </div>

          <div className="mission-action-row">
            <button
              type="button"
              className="button-secondary"
              onClick={() => setItems((prev) => [...prev, { question: "", context: "", my_answer: "" }])}
            >
              再加一道题
            </button>
            <button type="submit" className="mission-primary-cta" disabled={busy}>
              {busy ? "录入并评分中…" : "录入并评分"}
            </button>
          </div>

          {error ? (
            <p className="message error" role="alert">
              {error}
            </p>
          ) : null}
        </form>
      </section>
    </main>
  );
}
