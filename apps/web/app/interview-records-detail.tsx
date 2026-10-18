"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useState } from "react";

import {
  companyKeyFromName,
  evaluateInterviewRecord,
  readInterviewRecord,
  type InterviewRecord,
} from "./interview-records.ts";
import { ReferenceAnswerView } from "./reference-answer.tsx";
import type { ReferenceAnswerDetail } from "./fact-trust.ts";

export function InterviewRecordsDetail({ recordId }: { recordId: string }) {
  const [record, setRecord] = useState<InterviewRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [evaluating, setEvaluating] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setRecord(await readInterviewRecord(recordId));
    } catch (caught) {
      setRecord(null);
      setError(caught instanceof Error ? caught.message : "读取详情失败");
    } finally {
      setLoading(false);
    }
  }, [recordId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onEvaluate() {
    setEvaluating(true);
    setError("");
    try {
      setRecord(await evaluateInterviewRecord(recordId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "评分失败");
    } finally {
      setEvaluating(false);
    }
  }

  const companyHref = record
    ? (`/interview-records/company/${companyKeyFromName(record.company)}` as Route)
    : ("/interview-records" as Route);

  return (
    <main className="mission-home">
      <section className="mission-home-content">
        <p style={{ margin: 0 }}>
          <Link className="button-secondary" href={companyHref}>← 返回</Link>
        </p>
        {loading ? <p className="profile-note">读取中…</p> : null}
        {error ? (
          <p className="message error" role="alert">
            {error}
          </p>
        ) : null}
        {record ? (
          <>
            <div className="mission-heading mission-heading-compact">
              <div>
                <p className="eyebrow">面试记录详情</p>
                <h1>
                  {record.company}
                  {record.role ? ` · ${record.role}` : ""}
                </h1>
                <p className="summary">
                  {record.interviewed_on} · {record.interview_round} ·{" "}
                  {record.evaluated || record.status === "EVALUATED" ? "已评分" : "未评分"}
                </p>
              </div>
            </div>

            {!(record.evaluated || record.status === "EVALUATED") ? (
              <div className="mission-action-row">
                <button type="button" className="mission-primary-cta" disabled={evaluating} onClick={() => void onEvaluate()}>
                  {evaluating ? "评分中…" : "立即评分 / 生成复盘"}
                </button>
              </div>
            ) : null}

            <div className="debrief-grid">
              <div className="proof-card">
                <span className="status-chip">本场复盘</span>
                <h2>{record.gap_why || record.recommended_next_action || "保存后可生成复盘要点"}</h2>
                <p>
                  <b>下一步：</b>
                  {record.recommended_next_action || "完成评分后会给出补强方向"}
                </p>
                {record.gap_type ? (
                  <p>
                    <b>缺口类型：</b>
                    {record.gap_type}
                  </p>
                ) : null}
              </div>
              <div className="proof-card">
                <h3>做得好的地方</h3>
                {record.strong_points?.length ? (
                  record.strong_points.map((item) => <p key={item}>✓ {item}</p>)
                ) : (
                  <p className="muted">暂无</p>
                )}
                <h3>需要加强</h3>
                {record.weak_points?.length ? (
                  record.weak_points.map((item) => <p key={item}>! {item}</p>)
                ) : (
                  <p className="muted">暂无</p>
                )}
              </div>
            </div>

            <section className="proof-card interview-round-summary">
              <h3>逐题记录</h3>
              {record.items.map((item) => (
                <article className="interview-round" key={item.id}>
                  <strong>第 {item.sort_order + 1} 题</strong>
                  <p>
                    <b>问题：</b>
                    {item.question}
                  </p>
                  {item.context ? (
                    <p>
                      <b>内容 / 上下文：</b>
                      {item.context}
                    </p>
                  ) : null}
                  <p>
                    <b>我的回答：</b>
                    {item.my_answer}
                  </p>
                  {typeof item.evaluation?.score === "number" ? (
                    <p>
                      <b>评分：</b>
                      {item.evaluation.score} / 10
                    </p>
                  ) : null}
                  {item.evaluation?.strong_points?.length ? (
                    <p>
                      <b>做得好：</b>
                      {item.evaluation.strong_points.join("；")}
                    </p>
                  ) : null}
                  {item.evaluation?.weak_points?.length ? (
                    <p>
                      <b>可加强：</b>
                      {item.evaluation.weak_points.join("；")}
                    </p>
                  ) : null}
                  {item.evaluation?.reference_answer || item.evaluation?.reference_answer_detail ? (
                    <ReferenceAnswerView
                      title="参考回答"
                      detail={(item.evaluation?.reference_answer_detail as ReferenceAnswerDetail | undefined) ?? null}
                      text={item.evaluation?.reference_answer ?? null}
                    />
                  ) : null}
                  {item.evaluation?.recommended_next_action ? (
                    <p>
                      <b>建议：</b>
                      {item.evaluation.recommended_next_action}
                    </p>
                  ) : null}
                </article>
              ))}
            </section>

            <section className="proof-card">
              <h3>补强建议</h3>
              {record.coaching ? (
                <>
                  <p>
                    <strong>{record.coaching.title || "下一步怎么补强"}</strong>
                  </p>
                  <p>{record.coaching.summary}</p>
                  {record.coaching.questions?.length ? (
                    <>
                      <h4>建议追问自己</h4>
                      {record.coaching.questions.map((q) => (
                        <p key={q}>• {q}</p>
                      ))}
                    </>
                  ) : null}
                  {record.coaching.steps?.length ? (
                    <>
                      <h4>可执行步骤</h4>
                      {record.coaching.steps.map((step, index) => (
                        <p key={step}>
                          {index + 1}. {step}
                        </p>
                      ))}
                    </>
                  ) : null}
                  {record.coaching.learning?.length ? (
                    <>
                      <h4>补齐知识点</h4>
                      {record.coaching.learning.map((item) => (
                        <p key={item}>• {item}</p>
                      ))}
                    </>
                  ) : null}
                  {record.coaching.expected_outputs?.length ? (
                    <>
                      <h4>完成后形成</h4>
                      {record.coaching.expected_outputs.map((item) => (
                        <p key={item}>• {item}</p>
                      ))}
                    </>
                  ) : null}
                  {record.coaching.generated_by ? (
                    <p className="muted">来源：{record.coaching.generated_by}</p>
                  ) : null}
                </>
              ) : (
                <p className="muted">评分完成后会在这里给出补强建议。</p>
              )}
            </section>

            {record.notes ? (
              <section className="proof-card">
                <h3>备注</h3>
                <p>{record.notes}</p>
              </section>
            ) : null}
          </>
        ) : null}
      </section>
    </main>
  );
}
