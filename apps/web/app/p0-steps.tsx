"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { WorkflowSnapshot, WorkflowStep } from "./workflow-state.ts";
import type { WorkflowStepControls } from "./workflow-route.tsx";
import { createMarketProfileRequest } from "./market-profile.ts";
import { createGapAnalysisRequest } from "./gap-analysis.ts";
import { savePrioritiesRequest } from "./priorities.ts";
import { createRoadmapRequest, replanRoadmapRequest, RoadmapRequestError, updateRoadmapTaskRequest } from "./roadmap.ts";
import type { RoadmapTaskStatus } from "./roadmap.ts";
import { gapSeverityLabel, priorityDecisionReason, priorityLaneLabel, priorityLevelLabel, priorityMarketSummary, priorityStateLabel } from "./priority-ui.ts";
import { roadmapErrorMessage, roadmapUiState, taskStatusLabel } from "./roadmap-ui.ts";
import { runSingleFlight } from "./workflow-actions.ts";

type StepProps = { snapshot: WorkflowSnapshot; controls: WorkflowStepControls };

function Heading({ step, title, summary }: { step: string; title: string; summary: string }) {
  return <div className="step-heading"><p className="section-kicker">{step}</p><h1 id="workflow-step-title">{title}</h1><p className="summary">{summary}</p></div>;
}

function ErrorBox({ error, retry }: { error: string; retry: () => void }) {
  if (!error) return null;
  return <div className="workflow-inline-error" role="alert"><p>{error}</p><button type="button" className="button-secondary" onClick={retry}>重试</button></div>;
}

export function MarketProfileStep({ snapshot, controls }: StepProps) {
  const [record, setRecord] = useState(snapshot.marketProfile);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef<Promise<boolean> | null>(null);
  const generate = useCallback(() => runSingleFlight(generation, async () => {
    if (!snapshot.targetRole) return false;
    setLoading(true); setError("");
    try {
      const result = await createMarketProfileRequest(snapshot.targetRole.id, controls.apiUrl);
      setRecord(result); controls.setNextReady(true); await controls.refresh(); return true;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "市场画像暂时生成失败，请重试。"); return false; }
    finally { setLoading(false); }
  }), [controls, snapshot.targetRole]);
  const generateGap = useCallback(() => runSingleFlight(generation, async () => {
    if (!snapshot.profile) return false;
    setLoading(true); setError("");
    try {
      await createGapAnalysisRequest(snapshot.profile.profile_id, controls.apiUrl);
      await controls.refresh();
      return true;
    } catch (cause) { setError(cause instanceof Error ? cause.message : "差距分析暂时生成失败，请重试。"); return false; }
    finally { setLoading(false); }
  }), [controls, snapshot.profile]);
  useEffect(() => {
    controls.setNextReady(Boolean(record));
    controls.setNextAction(record ? (snapshot.gapAnalysis ? () => Promise.resolve(true) : generateGap) : null);
    return () => controls.setNextAction(null);
  }, [controls, generateGap, record, snapshot.gapAnalysis]);
  return <div className="workflow-step-content">
    <Heading step="Step 5 · Market Profile" title="看见真实岗位市场要求" summary="系统会从当前目标岗位的真实 JD 中提取并聚合显性要求；每一条要求都保留来源证据。" />
    <ErrorBox error={error} retry={() => void (record ? generateGap() : generate())} />
    {!record && <div className="workflow-callout"><p>已有 {snapshot.jobDescriptions.length} 条 JD。至少 3 条才能生成市场画像。</p><button type="button" disabled={loading} onClick={() => void generate()}>{loading ? "正在分析…" : "生成市场画像"}</button></div>}
    {record && <div className="p0-card-grid"><div className="p0-summary-card"><strong>{record.sample_count}</strong><span>条 JD 样本</span></div><div className="p0-summary-card"><strong>{record.capabilities.length}</strong><span>项能力维度</span></div><div className="p0-summary-card"><strong>{record.requirements.length}</strong><span>项原子要求（可展开）</span></div></div>}
    {record && <div className="p0-list">{record.capabilities.map((capability) => <article className="p0-card" key={capability.id}><div className="p0-card-title"><h2>{capability.name}</h2><span>{Math.round(capability.frequency_ratio * 100)}%</span></div><p>{capability.occurrence_count} / {record.sample_count} JDs</p><p>{capability.summary}</p><details><summary>查看底层要求与证据（{capability.atomic_requirements.length} 项，{capability.evidence.length} 条）</summary><ul>{capability.atomic_requirements.map((requirement) => <li key={requirement.id}><strong>{requirement.name}</strong><span> · {requirement.category} · {Math.round(requirement.frequency_ratio * 100)}%</span><details><summary>查看证据（{requirement.evidence.length}）</summary><ul>{requirement.evidence.map((evidence) => <li key={evidence.id}><blockquote>“{evidence.evidence_text}”</blockquote><small>JD {evidence.job_description_id.slice(0, 8)}{evidence.source_url ? ` · ${evidence.source_url}` : ""}</small></li>)}</ul></details></li>)}</ul></details></article>)}</div>}
  </div>;
}

export function GapAnalysisStep({ snapshot, controls }: StepProps) {
  const [record, setRecord] = useState(snapshot.gapAnalysis);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef<Promise<boolean> | null>(null);
  const generate = useCallback(() => runSingleFlight(generation, async () => {
    setLoading(true); setError("");
    try { const result = await createGapAnalysisRequest(snapshot.profile?.profile_id ?? "", controls.apiUrl); setRecord(result); controls.setNextReady(true); await controls.refresh(); return true; }
    catch (cause) { setError(cause instanceof Error ? cause.message : "差距分析暂时生成失败，请重试。"); return false; }
    finally { setLoading(false); }
  }), [controls, snapshot.profile?.profile_id]);
  useEffect(() => { controls.setNextReady(Boolean(record)); controls.setNextAction(() => record ? Promise.resolve(true) : generate()); return () => controls.setNextAction(null); }, [controls, generate, record]);
  return <div className="workflow-step-content">
    <Heading step="Step 6 · Gap Analysis" title="把市场要求和你的 Profile 对照" summary="差距状态只基于已确认 Profile 的事实；系统不会用简历草稿或推测的熟练度替代用户确认。" />
    <ErrorBox error={error} retry={() => void generate()} />
    {!record && <div className="workflow-callout"><p>市场画像已准备好，可以生成已匹配、部分具备、明显缺口和证据不足的结果。</p><button type="button" disabled={loading} onClick={() => void generate()}>{loading ? "正在比较…" : "生成差距分析"}</button></div>}
    {record && (record.gaps.length === 0
      ? <div className="workflow-callout"><p>当前市场要求都已在已确认 Profile 中找到匹配证据，暂无待处理差距。</p></div>
      : <div className="p0-list">{record.gaps.map((gap) => <article className={`p0-card gap-${gap.state.toLowerCase()}`} key={gap.id}><div className="p0-card-title"><h2>{gap.capability_name}</h2><span>{priorityStateLabel(gap.state)}</span></div><p>{Math.round(gap.frequency_ratio * 100)}% JD 提及 · 影响程度 {gapSeverityLabel(gap.severity)}</p><p>{gap.capability_summary}</p><p>{gap.rationale}</p><details><summary>查看底层要求与 JD 证据（{gap.atomic_requirement_names.length} 项，{gap.market_evidence.length} 条）</summary><ul>{gap.atomic_requirement_names.map((name) => <li key={name}>{name}</li>)}{gap.market_evidence.map((evidence) => <li key={evidence.id}><blockquote>“{evidence.evidence_text}”</blockquote><small>JD {evidence.job_description_id.slice(0, 8)}{evidence.source_url ? ` · ${evidence.source_url}` : ""}</small></li>)}</ul></details>{gap.evidence_refs.length > 0 && <small>已绑定 Profile 证据 {gap.evidence_refs.length} 条</small>}</article>)}</div>)}
  </div>;
}

export function PrioritiesStep({ snapshot, controls }: StepProps) {
  const [items, setItems] = useState(snapshot.priorities?.items ?? []);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { apiUrl, refresh } = controls;
  useEffect(() => { setItems(snapshot.priorities?.items ?? []); setDirty(false); }, [snapshot.priorities]);
  const persist = useCallback(async () => {
    if (!snapshot.profile || !items.length) return false;
    setSaving(true); setError("");
    try { await savePrioritiesRequest(snapshot.profile.profile_id, items.map((item) => item.gap_id), apiUrl); setDirty(false); await refresh(); return true; }
    catch (cause) { setError(cause instanceof Error ? cause.message : "优先级保存失败，请重试。"); return false; }
    finally { setSaving(false); }
  }, [apiUrl, items, refresh, snapshot.profile]);
  useEffect(() => { controls.setNextReady(Boolean(items.length)); controls.setNextAction(async () => { if (!snapshot.profile || !items.length) return false; if (!dirty && !snapshot.priorities?.overridden) return true; return persist(); }); return () => controls.setNextAction(null); }, [controls, dirty, items, persist, snapshot.priorities, snapshot.profile]);
  const move = (index: number, direction: -1 | 1) => { const next = [...items]; const target = index + direction; if (target < 0 || target >= next.length) return; [next[index], next[target]] = [next[target], next[index]]; setItems(next); setDirty(true); };
  const save = async () => { await persist(); };
  return <div className="workflow-step-content">
    <Heading step="第 7 步 · 优先级" title="决定现在最值得投入什么" summary="系统建议优先级并解释依据；你可以上下移动，最终顺序会保存为用户确认顺序。" />
    <ErrorBox error={error} retry={() => void save()} />
    {!items.length
      ? <div className="workflow-callout"><p>请先生成差距分析。</p></div>
      : <div className="p0-list">{items.map((item, index) => <article className="p0-card priority-card" key={item.gap_id}>
        <div className="priority-card-body">
          <div className="priority-card-heading">
            <span className="priority-rank" aria-label={`第 ${index + 1} 项`}>{index + 1}</span>
            <h2>{item.requirement_name}</h2>
            <span className="priority-stage">{priorityLaneLabel(item.lane)}</span>
          </div>
          <p className="priority-state">当前状态：{priorityStateLabel(item.state)}</p>
          <p className="priority-reason">{priorityDecisionReason(item)}</p>
          <p className="priority-market">市场证据：{priorityMarketSummary(item)}</p>
          <div className="priority-indicators" aria-label="优先级指标">
            <span>市场要求：{priorityLevelLabel(item.severity)}</span>
            <span>当前差距：{priorityLevelLabel(item.proximity)}</span>
            <span>短期改善可行性：{priorityLevelLabel(item.feasibility)}</span>
          </div>
        </div>
        <div className="priority-actions" aria-label="调整优先级顺序">
          <button type="button" className="button-secondary" disabled={index === 0 || saving} onClick={() => move(index, -1)}>上移</button>
          <button type="button" className="button-secondary" disabled={index === items.length - 1 || saving} onClick={() => move(index, 1)}>下移</button>
        </div>
      </article>)}</div>}
    {items.length > 0 && <button type="button" disabled={saving} onClick={() => void save()}>{saving ? "保存中…" : "保存我的排序"}</button>}
  </div>;
}

export function RoadmapStep({ snapshot, controls }: StepProps) {
  const [record, setRecord] = useState(snapshot.roadmap);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const generation = useRef<Promise<boolean> | null>(null);
  const gapNames = new Map((snapshot.gapAnalysis?.gaps ?? []).map((gap) => [gap.id, gap.requirement_name]));
  const state = roadmapUiState(record, loading, error);
  const generate = useCallback(() => runSingleFlight(generation, async () => {
    setLoading(true);
    setError("");
    try {
      const result = await createRoadmapRequest(snapshot.profile?.profile_id ?? "", controls.apiUrl);
      setRecord(result);
      controls.setNextReady(true);
      await controls.refresh();
      return true;
    } catch (cause) {
      setError(cause instanceof RoadmapRequestError ? cause.message : roadmapErrorMessage("NETWORK"));
      return false;
    } finally {
      setLoading(false);
    }
  }), [controls, snapshot.profile?.profile_id]);
  useEffect(() => {
    controls.setNextReady(state === "SUCCESS");
    controls.setNextAction(state === "SUCCESS" ? () => Promise.resolve(true) : state === "GENERATING" ? null : generate);
    return () => controls.setNextAction(null);
  }, [controls, generate, state]);
  return <div className="workflow-step-content">
    <Heading step="第 8 步 · 四周计划" title="把优先级变成四周行动" summary="每周目标、可衡量结果和每日任务都会受每周投入时间约束，并绑定到具体差距。" />
    {state === "ERROR" && <ErrorBox error={error} retry={() => void generate()} />}
    {state === "READY" && <div className="workflow-callout"><p>差距和优先级已准备好，可以生成四周行动计划。</p><button type="button" onClick={() => void generate()}>生成四周计划</button></div>}
    {state === "GENERATING" && <div className="workflow-callout" aria-live="polite"><p>正在生成四周计划，请稍候。</p></div>}
    {state === "SUCCESS" && <div className="p0-list">{(record?.weeks ?? []).map((week) => {
      const workload = week.tasks.reduce((total, task) => total + task.estimated_minutes, 0);
      const focusNames = week.focus_gap_ids.map((gapId) => gapNames.get(gapId) ?? "已绑定差距");
      return <article className="p0-card roadmap-week-card" key={week.id}>
        <div className="p0-card-title"><h2>第 {week.week_number} 周</h2><span>{week.tasks.length} 项任务</span></div>
        <p><strong>本周目标：</strong>{week.objective}</p>
        <p><strong>目标能力/差距：</strong>{focusNames.length ? focusNames.join("、") : "按当前优先级推进"}</p>
        <p><strong>可衡量结果：</strong>{week.measurable_outcome}</p>
        <p className="roadmap-workload"><strong>预计投入：</strong>{workload} 分钟</p>
        <ul>{week.tasks.map((task) => <li key={task.id}>{task.title} · {task.estimated_minutes} 分钟 · 关联差距：{task.gap_id ? gapNames.get(task.gap_id) ?? "已绑定" : "未绑定"}</li>)}</ul>
      </article>;
    })}</div>}
  </div>;
}

export function ProgressStep({ snapshot, controls }: StepProps) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const roadmap = snapshot.roadmap;
  const tasks = useMemo(() => roadmap?.weeks.flatMap((week) => week.tasks.map((task) => ({ ...task, week: week.week_number }))) ?? [], [roadmap]);
  const gapNames = useMemo(() => new Map((snapshot.gapAnalysis?.gaps ?? []).map((gap) => [gap.id, gap.requirement_name])), [snapshot.gapAnalysis]);
  useEffect(() => { controls.setNextReady(Boolean(roadmap)); controls.setNextAction(null); return () => controls.setNextAction(null); }, [controls, roadmap]);
  const update = async (taskId: string, status: RoadmapTaskStatus) => { setBusy(true); setError(""); try { await updateRoadmapTaskRequest(taskId, status, controls.apiUrl); await controls.refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : "任务状态保存失败，请重试。"); } finally { setBusy(false); } };
  const replan = async () => { if (!snapshot.profile) return; setBusy(true); setError(""); try { await replanRoadmapRequest(snapshot.profile.profile_id, 3, controls.apiUrl); await controls.refresh(); } catch (cause) { setError(cause instanceof Error ? cause.message : "重规划失败，请重试。"); } finally { setBusy(false); } };
  return <div className="workflow-step-content"><Heading step="第 9 步 · 执行进度" title="按执行结果调整计划" summary="完成和跳过只记录执行状态，不会冒充技能掌握；重新规划由你主动触发。" /><ErrorBox error={error} retry={() => void replan()} />{!roadmap ? <div className="workflow-callout"><p>请先生成四周计划。</p></div> : <><div className="p0-summary-card"><strong>{Math.round(roadmap.progress_ratio * 100)}%</strong><span>当前完成度</span></div><div className="p0-list">{tasks.map((task) => <article className="p0-card" key={task.id}><div className="p0-card-title"><h2>第 {task.week} 周 · {task.title}</h2><span>{taskStatusLabel(task.status)}</span></div><p>{task.objective} · {task.estimated_minutes} 分钟</p><small>关联差距：{task.gap_id ? gapNames.get(task.gap_id) ?? "已绑定" : "未绑定"} · 完成标准：{task.completion_criteria}</small><div className="priority-actions"><button type="button" className="button-secondary" disabled={busy} onClick={() => void update(task.id, "DONE")}>完成</button><button type="button" className="button-secondary" disabled={busy} onClick={() => void update(task.id, "SKIPPED")}>跳过</button></div></article>)}</div><button type="button" disabled={busy} onClick={() => void replan()}>{busy ? "处理中…" : "重新规划剩余计划"}</button></>}</div>;
}

export function DashboardStep({ snapshot, controls }: StepProps) {
  useEffect(() => { controls.setNextReady(false); controls.setNextAction(null); return () => controls.setNextAction(null); }, [controls]);
  const dashboard = snapshot.dashboard;
  return <div className="workflow-step-content"><Heading step="Step 10 · Dashboard" title="知道现在发生了什么，下一步做什么" summary="Dashboard 只聚合已经保存的目标岗位、市场证据、差距、优先级、计划和进度。" />{!dashboard ? <div className="workflow-callout"><p>Dashboard 数据尚未准备好，请从前面的步骤继续。</p></div> : <div className="p0-dashboard-grid"><section className="p0-card"><h2>当前目标岗位</h2><p>{dashboard.target_role?.role_name ?? "未选择"}</p><p>{dashboard.jd_sample_count} 条 JD · {dashboard.market_ready ? "市场画像已准备" : "尚未达到分析条件"}</p></section><section className="p0-card"><h2>当前进度</h2><p>第 {dashboard.current_week ?? "—"} 周 · {Math.round(dashboard.progress_ratio * 100)}%</p></section><section className="p0-card"><h2>Top Market Requirements</h2><ul>{dashboard.top_requirements.map((item) => <li key={item.name}>{item.name} · {Math.round(item.frequency_ratio * 100)}%</li>)}</ul></section><section className="p0-card"><h2>Top Gaps</h2><ul>{dashboard.top_gaps.map((gap) => <li key={gap.id}>{gap.requirement_name} · {gap.state}</li>)}</ul></section><section className="p0-card"><h2>Upcoming Tasks</h2><ul>{dashboard.upcoming_tasks.map((task) => <li key={task.id}>{task.title}</li>)}</ul></section></div>}</div>;
}

export type P0Step = WorkflowStep;
