"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import {
  createTargetJob,
  generateClaimAnalysis,
  generateProofGuidance,
  generateProofActions,
  startInterview,
  submitInterviewAnswer,
} from "./proof-flow.ts";
import type { ProofSnapshot, ProofStep } from "./proof-state.ts";
import { saveLastMockDebrief, summarizeMockDebrief } from "./mission-state.ts";
import { freshInterviewEntry } from "./proof-state.ts";
import type { ProofStepControls } from "./proof-route.tsx";

type Props = { step: ProofStep; snapshot: ProofSnapshot; controls: ProofStepControls; freshStart?: boolean };
type InterviewPhase = "QUESTION_READY" | "ANSWERING" | "SUBMITTING" | "EVALUATED" | "NEXT_QUESTION" | "COMPLETED";

function PanelHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) {
  return <header className="step-heading"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><p className="step-description">{description}</p></header>;
}

function proofActionStatusLabel(status: string): string {
  return ({ PROPOSED: "待开始", IN_PROGRESS: "进行中", COMPLETED: "已完成", SKIPPED: "已跳过" } as Record<string, string>)[status] ?? "待开始";
}

function proofActionTypeLabel(type: string): string {
  return type === "FACT_QA_NOTES" ? "事实追问" : type === "PROJECT_WRITEUP" ? "项目补全" : "补强";
}

export function ProofStepView({ step, snapshot, controls, freshStart = false }: Props) {
  const { setNextReady, setNextAction, setStepError } = controls;
  const freshHandledRef = useRef(false);
  const [jobText, setJobText] = useState(snapshot.targetJob?.raw_text ?? "");
  const [sourceUrl, setSourceUrl] = useState(snapshot.targetJob?.source_url ?? "");
  const [answer, setAnswer] = useState("");
  const [interviewPhase, setInterviewPhase] = useState<InterviewPhase>("QUESTION_READY");
  const [interviewStarting, setInterviewStarting] = useState(false);
  const [selectedClaimId, setSelectedClaimId] = useState(snapshot.claim?.id ?? "");
  const [selectedActionId, setSelectedActionId] = useState(snapshot.actions[0]?.id ?? "");
  const [guidance, setGuidance] = useState<Awaited<ReturnType<typeof generateProofGuidance>> | null>(null);
  const [guidanceLoading, setGuidanceLoading] = useState(false);

  const selectedClaim = useMemo(() => snapshot.analysis?.claims.find((claim) => claim.id === selectedClaimId) ?? snapshot.claim, [selectedClaimId, snapshot.analysis, snapshot.claim]);
  const selectedAction = useMemo(() => snapshot.actions.find((action) => action.id === selectedActionId) ?? snapshot.actions[0], [selectedActionId, snapshot.actions]);

  useEffect(() => {
    if (step !== "target-job") return;
    setNextReady(Boolean(snapshot.targetJob || jobText.trim()));
    setNextAction(async () => {
      if (!jobText.trim()) { setStepError("请粘贴一份目标岗位描述。"); return false; }
      await createTargetJob(controls.profileId, jobText, sourceUrl || null, controls.apiUrl);
      return true;
    });
  }, [controls.apiUrl, controls.profileId, jobText, setNextAction, setNextReady, setStepError, snapshot.targetJob, sourceUrl, step]);

  useEffect(() => {
    if (step !== "resume-suggestions") return;
    const hasClaims = Boolean(snapshot.analysis?.claims.length);
    setNextReady(hasClaims || Boolean(snapshot.targetJob));
    // Footer「继续：主张核对」must generate via the same path as a successful left-rail visit.
    setNextAction(
      hasClaims
        ? null
        : async () => {
            if (!snapshot.targetJob) {
              setStepError("还没有目标岗位，请先保存岗位描述。");
              return false;
            }
            try {
              setStepError("");
              await generateClaimAnalysis(snapshot.targetJob.id, controls.apiUrl);
              await controls.refresh();
              return true;
            } catch (err) {
              const raw = err instanceof Error ? err.message : "";
              if (/Claim analysis has not been generated|尚未生成主张分析/i.test(raw)) {
                setStepError("主张分析还没生成成功，请稍后重试。");
              } else {
                setStepError(raw || "主张分析生成失败，请重试。");
              }
              return false;
            }
          },
    );
  }, [controls.apiUrl, controls.refresh, setNextAction, setNextReady, setStepError, snapshot.analysis, snapshot.targetJob, step]);

  useEffect(() => {
    if (step !== "claim-check") return;
    setNextReady(Boolean(selectedClaim));
    setNextAction(selectedClaim && !snapshot.session ? async () => {
      const started = await startInterview(selectedClaim.id, controls.apiUrl);
      controls.setSnapshot({ ...snapshot, session: started, sessions: [started, ...snapshot.sessions] });
      return true;
    } : null);
  }, [controls.apiUrl, controls.setSnapshot, selectedClaim, setNextAction, setNextReady, snapshot, snapshot.session, step]);

  useEffect(() => {
    if (step !== "interview") return;
    const claim = selectedClaim || snapshot.claim;
    if (!claim) {
      setInterviewStarting(false);
      setNextReady(false);
      setNextAction(null);
      setStepError("还没有可追问的简历主张。请先生成主张分析并完成主张核对。");
      return;
    }
    const session = snapshot.session;
    // Mission CTA ?fresh=1: start a new session instead of resuming mid-flow (第 2+ 轮) or a completed one.
    const freshDecision = freshInterviewEntry(freshStart, freshHandledRef.current, session);
    const shouldFreshStart = freshDecision.startNew;
    if (freshDecision.consumeFresh) freshHandledRef.current = true;
    if (session && !shouldFreshStart) {
      setInterviewStarting(false);
      setStepError("");
      setNextReady(session.status !== "COMPLETED");
      return;
    }
    let cancelled = false;
    const apiUrl = controls.apiUrl;
    const refresh = controls.refresh;
    setNextReady(false);
    setNextAction(null);
    setInterviewStarting(true);
    void (async () => {
      try {
        setStepError("");
        const started = await startInterview(claim.id, apiUrl);
        if (!cancelled) {
          controls.setSnapshot({ ...snapshot, session: started, sessions: [started, ...snapshot.sessions] });
          setInterviewStarting(false);
        }
      } catch (err) {
        if (!cancelled) {
          if (shouldFreshStart) freshHandledRef.current = false;
          setInterviewStarting(false);
          setStepError(err instanceof Error ? err.message : "无法开始模拟面试，请稍后重试。");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [controls.apiUrl, controls.setSnapshot, freshStart, selectedClaim, setNextAction, setNextReady, setStepError, snapshot, snapshot.claim, snapshot.session, step]);

  useEffect(() => {
    if (step !== "interview") return;
    const complete = snapshot.session?.status === "COMPLETED";
    setInterviewPhase(complete ? "COMPLETED" : (snapshot.session?.turns?.some((turn) => turn.answer != null) ? "EVALUATED" : "QUESTION_READY"));
    setNextReady(Boolean(complete || answer.trim()));
    setNextAction(!complete && snapshot.session && answer.trim() ? async () => {
      const submittedAnswer = answer.trim();
      setInterviewPhase("SUBMITTING");
      try {
        const updated = await submitInterviewAnswer(snapshot.session!.id, submittedAnswer, controls.apiUrl);
        controls.setSnapshot({ ...snapshot, session: updated, sessions: [updated, ...snapshot.sessions.filter((item) => item.id !== updated.id)] });
        setAnswer("");
        setInterviewPhase(updated.status === "COMPLETED" ? "COMPLETED" : "NEXT_QUESTION");
        setStepError("");
        return true;
      } catch (err) {
        setInterviewPhase("ANSWERING");
        setStepError(err instanceof Error ? `提交回答失败：${err.message}` : "提交回答失败，请重试。输入内容已保留。");
        return false;
      }
    } : null);
    if (complete && snapshot.session?.mission_id) {
      const summarized = summarizeMockDebrief(snapshot.session);
      if (summarized) saveLastMockDebrief(String(snapshot.session.mission_id), summarized);
    }
  }, [answer, controls.apiUrl, controls.setSnapshot, setNextAction, setNextReady, setStepError, snapshot, snapshot.session, step]);

  useEffect(() => {
    if (step !== "debrief") return;
    setNextReady(snapshot.session?.status === "COMPLETED");
    setNextAction(null);
    const session = snapshot.session;
    const missionId = session?.mission_id;
    if (session?.status === "COMPLETED" && missionId) {
      const summarized = summarizeMockDebrief(session);
      if (summarized) saveLastMockDebrief(String(missionId), summarized);
    }
  }, [setNextAction, setNextReady, snapshot.session, step]);

  useEffect(() => {
    if (step !== "proof-actions") return;
    setNextReady(Boolean(snapshot.actions.length || snapshot.session?.status === "COMPLETED"));
    setNextAction(snapshot.actions.length ? null : async () => {
      if (!snapshot.claim) return false;
      await generateProofActions(snapshot.claim.id, controls.apiUrl);
      return true;
    });
  }, [controls.apiUrl, setNextAction, setNextReady, snapshot.actions, snapshot.claim, snapshot.session, step]);

  useEffect(() => {
    if (step !== "re-evaluate") return;
    setNextReady(false);
    setNextAction(null);
  }, [setNextAction, setNextReady, step]);

  if (step === "target-job") {
    return <div className="step-body"><PanelHeading eyebrow="01 · 目标岗位" title="从一份真实岗位开始" description="粘贴你正在申请或认真考虑的岗位描述。系统会保留原文，并用它生成可追溯的简历主张。" /><label className="field-label" htmlFor="target-job-text">岗位描述</label><textarea id="target-job-text" className="textarea" rows={13} value={jobText} onChange={(event) => setJobText(event.target.value)} placeholder="粘贴岗位职责、要求和业务背景…" /><label className="field-label" htmlFor="target-job-url">来源链接（可选）</label><input id="target-job-url" className="text-input" value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} placeholder="https://…" />{snapshot.targetJob && <p className="message success">已保存一份目标岗位。继续会保存当前编辑内容。</p>}</div>;
  }

  if (step === "resume-suggestions") {
    return <div className="step-body"><PanelHeading eyebrow="02 · 简历建议" title="把岗位要求映射到你的经历" description="每条建议都保留原文、修改理由、证据引用和风险提示。生成后先逐条检查，再进入面试。" />{snapshot.analysis?.claims.length ? <div className="proof-card-list">{snapshot.analysis.claims.map((claim) => <article className="proof-card" key={claim.id}><div className="proof-card-header"><span className={`status-chip status-${claim.readiness_status.toLowerCase()}`}>{claim.readiness_status}</span><strong>{claim.claim}</strong></div><p><b>当前：</b>{claim.current_text || "未找到对应表述"}</p><p><b>建议：</b>{claim.suggested_text || "保留原文，先补证据"}</p><p><b>理由：</b>{claim.reason}</p><p><b>证据来源：</b>{claim.evidence_refs.length ? `${claim.evidence_refs.length} 条档案证据` : "暂无可引用 evidence"}</p><p><b>风险：</b>{claim.risk_reason}</p><p className="muted">JD 相关性：{claim.jd_relevance}</p></article>)}</div> : <div className="empty-state"><p>还没有生成建议。</p><p className="muted">点击右下角继续，调用严格 JSON 输出并保存分析结果。</p></div>}</div>;
  }

  if (step === "claim-check") {
    return <div className="step-body"><PanelHeading eyebrow="03 · 主张核对" title="先挑一条主张做压力测试" description="选择一条你愿意在面试中捍卫的简历主张。系统会展示它的攻击面，再开始最多五轮的追问。" />{snapshot.analysis?.claims.map((claim) => <label className="proof-select-card" key={claim.id}><input type="radio" name="claim" checked={selectedClaimId === claim.id} onChange={() => setSelectedClaimId(claim.id)} /><span><strong>{claim.claim}</strong><small>{claim.readiness_status} · 信心 {Math.round(claim.confidence * 100)}%</small><em>{claim.attack_surface.map((item) => `${item.area}: ${item.risk}`).join("；") || "等待面试压力测试"}</em></span></label>)}</div>;
  }

  if (step === "interview") {
    const session = snapshot.session;
    const complete = session?.status === "COMPLETED";
    const pendingTurn = session?.turns?.find((turn) => turn.answer == null);
    const lastAnsweredTurn = [...(session?.turns ?? [])].reverse().find((turn) => turn.answer != null);
    const evaluation = lastAnsweredTurn?.evaluation ?? {};
    const displayRound = complete
      ? (lastAnsweredTurn?.round_number ?? session?.round_count ?? 0)
      : (pendingTurn?.round_number ?? (session?.round_count ?? 0) + 1);
    const questionReady = Boolean(session?.next_question);
    const questionStatus = interviewPhase === "SUBMITTING" ? "正在评分…" : interviewPhase === "NEXT_QUESTION" ? "下一题已生成" : questionReady ? "待回答" : "正在生成…";
    return <div className="step-body"><PanelHeading eyebrow="模拟面试" title={`回答第 ${displayRound} 题`} description="先回答当前问题，提交后记录评分、优点和待补强点，再进入补强建议和面试记录。" />{lastAnsweredTurn ? <div className="message success"><strong>本题评价：{typeof evaluation.score === "number" ? `${evaluation.score} / 10` : "已完成"}</strong>{evaluation.strong_points?.length ? <p>做得好的地方：{evaluation.strong_points.slice(0, 2).join("；")}</p> : null}{evaluation.weak_points?.length ? <p>可以加强：{evaluation.weak_points.slice(0, 2).join("；")}</p> : null}{evaluation.reference_answer ? <p>参考回答：{evaluation.reference_answer}</p> : null}</div> : null}{session?.status === "COMPLETED" ? <div className="message success">面试已完成，可以查看本轮记录。</div> : <><div className="interview-question"><span>第 {displayRound} 题 · {questionStatus}</span><h2>{session?.next_question || (interviewStarting ? "正在生成第 1 题，请稍候…" : "暂未生成问题，请点击重试")}</h2></div><textarea className="textarea interview-answer" rows={10} disabled={!questionReady || interviewPhase === "SUBMITTING"} value={answer} onChange={(event) => { setInterviewPhase("ANSWERING"); setAnswer(event.target.value); }} placeholder={questionReady ? "用具体事实、决策和结果回答…" : "问题生成完成后即可作答…"} /><p className="muted">提交后会显示评分、做得好的地方和参考回答。</p></>}</div>;
  }

  if (step === "debrief") {
    const session = snapshot.session;
    if (!session) return <div className="step-body"><PanelHeading eyebrow="面试记录" title="看看这次表现" description="完成面试后，这里会汇总每一道题、你的回答和下一步补强建议。" /><p className="message error">还没有完成的面试记录。</p></div>;
    const overall = session.gap_why || session.recommended_next_action || "本轮回答已完成，下面汇总每一题的表现。";
    return <div className="step-body"><PanelHeading eyebrow="面试记录" title="看看这次表现" description="这里汇总所有问题和回答，并给出项目补齐方向。" /><div className="debrief-grid"><div className="proof-card"><span className="status-chip">本次表现</span><h2>{overall}</h2><p><b>下一步：</b>{session.recommended_next_action || "根据需要加强的部分补全项目背景、个人动作和结果。"}</p></div><div className="proof-card"><h3>做得好的地方</h3>{session.strong_points.length ? session.strong_points.map((item) => <p key={item}>✓ {item}</p>) : <p className="muted">本轮没有记录到额外优势。</p>}<h3>需要加强</h3>{session.weak_points.length ? session.weak_points.map((item) => <p key={item}>! {item}</p>) : <p className="muted">本轮没有记录到明显弱项。</p>}</div></div><section className="proof-card interview-round-summary"><h3>逐题记录</h3>{session.turns.map((turn) => <article className="interview-round" key={turn.id}><strong>第 {turn.round_number} 题</strong><p><b>问题：</b>{turn.question}</p><p><b>回答：</b>{turn.answer || "未回答"}</p>{typeof turn.evaluation.score === "number" ? <p><b>评分：</b>{turn.evaluation.score} / 10</p> : null}{turn.evaluation.weak_points?.length ? <p><b>本题待加强：</b>{turn.evaluation.weak_points.join("；")}</p> : null}</article>)}</section><section className="proof-card"><h3>项目补齐建议</h3><p>{session.recommended_next_action || "围绕面试中暴露的缺口，补全项目背景、你的个人动作和可核对结果。"}</p>{session.weak_points.map((item) => <p key={`guide-${item}`}>• {item}</p>)}</section></div>;
  }

  if (step === "proof-actions") {
    return <div className="step-body"><PanelHeading eyebrow="面试补强" title="根据这次回答继续补强" description="只保留两种方式：回答事实追问，或按项目指南补全背景、个人动作和结果。" />{snapshot.actions.length ? <div className="proof-card-list">{snapshot.actions.map((action) => <label className="proof-select-card" key={action.id}><input type="radio" name="action" checked={selectedActionId === action.id} onChange={() => setSelectedActionId(action.id)} /><span><strong>{action.title}</strong><small>{proofActionTypeLabel(action.artifact_type)} · {action.estimated_hours} 小时 · {proofActionStatusLabel(action.status)}</small><em>{action.definition_of_done}</em></span></label>)}</div> : <p className="message">正在生成两种补强方式，请稍候。</p>}</div>;
  }

  async function generateGuidanceFor(actionType: "FACT_QA_NOTES" | "PROJECT_WRITEUP") {
    if (!selectedClaim) { setStepError("没有找到本轮面试对应的主张，请返回面试记录后重试。"); return; }
    setGuidanceLoading(true);
    setStepError("");
    try {
      setGuidance(await generateProofGuidance(selectedClaim.id, actionType, controls.apiUrl));
    } catch (err) {
      setStepError(err instanceof Error ? `生成补强建议失败：${err.message}` : "生成补强建议失败，请重试。");
    } finally {
      setGuidanceLoading(false);
    }
  }

  return <div className="step-body"><PanelHeading eyebrow="07 · AI 补强建议" title="让 AI 告诉你下一步怎么补强" description="选择事实追问或项目补全，直接生成下一步建议，不需要提交链接或证明材料。" />{guidance ? <div className="proof-card"><div className="proof-card-header"><span className="status-chip">{guidance.generated_by === "llm" ? "AI 已生成" : "备用建议"}</span><strong>{guidance.title}</strong></div><p>{guidance.summary}</p>{guidance.questions.length ? <><h3>接下来回答这些问题</h3>{guidance.questions.map((item) => <p key={item}>？ {item}</p>)}</> : null}{guidance.steps.length ? <><h3>项目补全步骤</h3>{guidance.steps.map((item, index) => <p key={item}>{index + 1}. {item}</p>)}</> : null}{guidance.learning.length ? <><h3>建议补充的知识</h3>{guidance.learning.map((item) => <p key={item}>• {item}</p>)}</> : null}{guidance.expected_outputs.length ? <><h3>完成后形成</h3>{guidance.expected_outputs.map((item) => <p key={item}>• {item}</p>)}</> : null}</div> : <div className="proof-card-list"><button type="button" className="proof-select-card guidance-choice" disabled={guidanceLoading} onClick={() => void generateGuidanceFor("FACT_QA_NOTES")}><strong>再问 3–5 个事实问题</strong><span>继续追问时间、角色、个人动作、决策和结果。</span></button><button type="button" className="proof-select-card guidance-choice" disabled={guidanceLoading} onClick={() => void generateGuidanceFor("PROJECT_WRITEUP")}><strong>补齐项目背景 / 个人动作 / 结果</strong><span>AI 给出项目改写建议、学习重点和可执行产出。</span></button>{guidanceLoading ? <p className="message">AI 正在生成建议，请稍候…</p> : null}</div>}</div>;
}
