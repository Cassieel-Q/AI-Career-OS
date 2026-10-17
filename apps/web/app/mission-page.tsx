"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

import { alignedExperienceWhy, missingExperienceLabel } from "./experience-utils.ts";
import {
  EXPERIENCE_DECISION_OPTIONS,
  advanceMission,
  bindMissionResumePdf,
  bindMissionResumeText,
  confirmResumeSource,
  readMasterResumeImpact,
  confirmStrategy,
  confirmTargetResume,
  generateMissionStep,
  generateProofActionsForMission,
  submitMissionProofArtifact,
  ingestResumePdf,
  ingestResumeText,
  isDebugMode,
  MISSION_API_BASE_URL,
  missionHref,
  readExperienceSelection,
  readInterviewPack,
  readMission,
  readProfile,
  readProofState,
  readMissionProofSnapshot,
  readReadiness,
  readRedTeam,
  readTargetResumes,
  recoverEvidence,
  regenerateResumeOptimization,
  retryCompanyIntel,
  saveExperienceSelection,
  submitMissionOutcome,
  reanalyzeMission,
  updateMissionIdentity,
  updateResumeBullet,
} from "./missions.ts";
import { upsertProfileLabelFromFilename } from "./profile-label.ts";
import { MissionProfileConfirmCard } from "./mission-profile-confirm.tsx";
import { buildTargetResumeExportHtml, countExportableBullets, exportEmptyContentFeedback, exportEntryHint, exportPrintWindowFeedback } from "./export-target-resume.ts";
import { buildPreExportChecklist, buildExportFileName, resolveExportProfileId } from "./export-resume-checks.ts";
import type {
  ExperienceSelection,
  Mission,
  MissionTab,
  ProfileExperience,
  ProofState,
  Readiness,
  ProfileSnapshot,
  TargetResume,
} from "./missions.ts";
import { readTargetJob, type TargetJob } from "./proof-flow.ts";
import { MissionShell } from "./mission-shell.tsx";
import { BossKitPanel } from "./boss-kit.tsx";
import { MissionMatchCard } from "./mission-match-card.tsx";
import { deriveMissionProgress } from "./mission-progress.ts";
import { TaskProgress } from "./task-progress.tsx";
import { withTaskTimeout } from "./task-progress.ts";
import { factConfirmationPatch, isChosenRewrite, resumeDecisionProgress } from "./resume-decision.ts";
import {
  countHighRiskFindings,
  CORE_RESUME_SUGGESTION_LIMIT,
  coreInterviewCopy,
  coreResumeNextStep,
  deriveResumeSubstep,
  describeJdAnalysisDegradation,
  humanizeMissionError,
  readinessStatusLabel,
  strengthenStatusSummary,
  validateMissionDebrief,
  nextRoute,
  normalizeWorkflowState,
  primaryCta,
  resumeStepTitle,
  summarizeIntelCoverage,
  targetResumeBulletDisplayText,
  buildTargetResumeInlineEditPatch,
  targetResumeBulletStatusLabel,
  workflowStateLabel,
  isUnknownIdentity,
  identityInputValue,
  seniorityLabel,
  locationLabel,
  missionIdentityLabel,
  buildCapabilityEvidenceView,
  buildJdRequirementEvidenceCoverage,
  classifyIntelSource,
  intelSourceTypeLabel,
  partitionIntelBySource,
  PENDING_CONFIRM_LABEL,
  COMPANY_PENDING_LABEL,
  COMPANY_INPUT_PLACEHOLDER,
  isRedTeamExecuted,
  normalizeRedTeamReport,
  redTeamResultCopy,
  parseEvidenceGapCount,
  hasInterviewableClaim,
  resolveInterviewTabCta,
  buildInterviewTabCompactHints,
  canAdvanceStrengthenEvent,
  mockInterviewHref,
  mockDebriefHref,
  resolveLastMockDebrief,
  type LastMockDebrief,
  looksLikePlaceholderResume,
  boundResumeSourceSummary,
  markProofVisited,
  hasVisitedProofForMission,
  claimStrengthenProgressLabel,
  resolveProofNextStep,
  proofActionStatusLabel,
  hasCompletedNoExperienceAction,
} from "./mission-state.ts";

type MissionPageProps = { missionId: string; currentTab: MissionTab | "overview" };


function boundProfileIdOf(mission: Mission | null): string | null {
  const raw = mission?.resume_source?.bound_profile_id;
  return typeof raw === "string" && raw.trim() ? raw.trim() : null;
}

/** Profile id for in-mission confirm card: mission_local bind, or Master profile when mode=master. */
function confirmableProfileIdOf(mission: Mission | null): string | null {
  const bound = boundProfileIdOf(mission);
  if (bound) return bound;
  const mode = mission?.resume_source?.mode;
  const masterId = mission?.profile_id;
  if (mode === "master" && typeof masterId === "string" && masterId.trim()) {
    return masterId.trim();
  }
  return null;
}

function resumeSourceLine(mission: Mission | null, experiences: ProfileExperience[]): string {
  const summary = boundResumeSourceSummary(mission, {
    experienceTitle: experiences[0]?.title || null,
  });
  return summary?.line || "尚未绑定简历";
}



function listOf(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === "object")) : [];
}

function stringsOf(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const item of value) {
    if (typeof item === "string" && item.trim()) out.push(item.trim());
    else if (item && typeof item === "object") {
      const rec = item as Record<string, unknown>;
      const pick = [rec.question, rec.text, rec.prompt, rec.followup, rec.follow_up].find((v) => typeof v === "string" && String(v).trim());
      if (typeof pick === "string" && pick.trim()) out.push(pick.trim());
    }
  }
  return out;
}

function followupsOf(finding: Record<string, unknown>): string[] {
  return stringsOf(finding.likely_followups ?? finding.followups ?? finding.likely_questions ?? finding.probes);
}

function textOf(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function stripEvidenceDump(text: string): string {
  return text
    .replace(/(?:\n|\r|\s)*Evidence\s*:\s*[\s\S]*$/i, "")
    .replace(/(?:\n|\r|\s)*(?:证据|依据)\s*[：:][\s\S]*$/i, "")
    .replace(/[（(]\s*(?:dogfood-req-[\w-]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*[）)]/gi, "")
    .replace(/\b(?:dogfood-req-[\w-]+|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b/gi, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim()
    .replace(/^[，。；、,;\s]+|[，。；、,;\s]+$/g, "");
}

function dedupeExperienceSelections<T extends { id: string; experience_id: string; why?: string }>(
  rows: T[],
  experienceMap: Map<string, ProfileExperience>,
): T[] {
  const seenIds = new Set<string>();
  const seenLabels = new Set<string>();
  const out: T[] = [];
  for (const row of rows) {
    if (seenIds.has(row.experience_id)) continue;
    seenIds.add(row.experience_id);
    const exp = experienceMap.get(row.experience_id);
    const label = `${(exp?.organization || "").trim().toLowerCase()}||${(exp?.title || "").trim().toLowerCase()}`;
    if (label !== "||" && seenLabels.has(label)) continue;
    if (label !== "||") seenLabels.add(label);
    out.push({ ...row, why: stripEvidenceDump(String(row.why || "")) } as T);
  }
  return out;
}

function formatEvidenceLabels(refs: string[] | undefined, experienceMap: Map<string, ProfileExperience>): string {
  if (!refs?.length) return "无";
  const labels: string[] = [];
  for (const ref of refs) {
    const exp = experienceMap.get(ref);
    if (exp) {
      const title = (exp.title || "").trim() || "未命名经历";
      const org = (exp.organization || "").trim();
      labels.push(org ? `${title} · ${org}` : title);
      continue;
    }
    // Never show raw UUIDs or dogfood-req-* ids to users
    if (/^dogfood-req-/i.test(ref) || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(ref)) {
      labels.push("来自已确认的简历经历");
      continue;
    }
    labels.push("来自已确认的简历经历");
  }
  // de-dupe while preserving order
  return Array.from(new Set(labels)).join(" · ") || "—";
}


function PrimaryButton({ children, onClick, disabled = false }: { children: ReactNode; onClick?: () => void; disabled?: boolean }) {
  return (
    <button type="button" className="mission-primary-cta" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

function TextButton({ children, onClick, disabled = false }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" className="mission-text-btn" onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}

function StructuredRewrite({ text }: { text: string }) {
  let points = text.split(/\r?\n/).map((point) => point.trim().replace(/^[•\-–]\s*/, "")).filter(Boolean);
  if (points.length < 2 && text.length > 60) {
    const segments = text.split("；").map((segment) => segment.trim()).filter(Boolean);
    if (segments.length >= 2) {
      points = segments.map((segment, index) => (index < segments.length - 1 && !/[；.;。]$/.test(segment) ? segment + "；" : segment));
    }
  }
  if (points.length < 2) return <>{text}</>;
  return <ul className="resume-structured-points">{points.map((point, index) => <li key={`${index}-${point}`}>{point}</li>)}</ul>;
}

function WhyPoints({ text }: { text: string }) {
  const cleaned = (text || "").trim();
  if (!cleaned) return null;
  // 在句号/分号后紧跟「中文标签：」的位置断行，把 AI 建议拆成要点列表
  const parts = cleaned.split(/(?<=[。；])\s*(?=[\u4e00-\u9fa5]{2,8}：)/).filter(Boolean);
  if (parts.length < 2) return <p>{cleaned}</p>;
  return <ul className="resume-structured-points">{parts.map((part, index) => <li key={`${index}-${part.slice(0, 12)}`}>{part}</li>)}</ul>;
}

function confirmedProjectTitle(title?: string | null) {
  return (title || "").replace(/^项目草案\s*[:：—-]?\s*/, "").trim() || "作品集项目";
}

export function MissionPage({ missionId, currentTab }: MissionPageProps) {
  const router = useRouter();
  const [mission, setMission] = useState<Mission | null>(null);
  const [targetJob, setTargetJob] = useState<TargetJob | null>(null);
  const [targetJobError, setTargetJobError] = useState(false);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [resumes, setResumes] = useState<TargetResume[]>([]);
  const [experienceSelection, setExperienceSelection] = useState<ExperienceSelection[]>([]);
  const [experiences, setExperiences] = useState<ProfileExperience[]>([]);
  const [sourceProfile, setSourceProfile] = useState<ProfileSnapshot | null>(null);
  const [redTeam, setRedTeam] = useState<{ id?: string; created_at?: string; findings: Array<Record<string, unknown>> }>({ findings: [] });
  /** False until first readRedTeam settles — avoids empty-report flicker. */
  const [redTeamSettled, setRedTeamSettled] = useState(false);
  const [interviewPack, setInterviewPack] = useState<{ topics: Array<Record<string, unknown>> }>({ topics: [] });
  const [lastMockDebrief, setLastMockDebrief] = useState<LastMockDebrief | null>(null);
  const [interviewSessionStatus, setInterviewSessionStatus] = useState<string | null>(null);
  const [optimizationStage, setOptimizationStage] = useState<number | null>(null);
  const [optimizationError, setOptimizationError] = useState("");
  const [regenerationFailed, setRegenerationFailed] = useState(false);
  const [resumeParseStage, setResumeParseStage] = useState<number | null>(null);
  const [questionStage, setQuestionStage] = useState<number | null>(null);
  const [questionError, setQuestionError] = useState("");
  const [highlightedExperienceId, setHighlightedExperienceId] = useState<string | null>(null);
  const [finalPreviewMode, setFinalPreviewMode] = useState<"original" | "target">("target");
  const finalPreviewRef = useRef<HTMLDivElement | null>(null);
  const [proof, setProof] = useState<ProofState | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [savingDecision, setSavingDecision] = useState(false);
  const [error, setError] = useState("");
  const [proofNotice, setProofNotice] = useState("");
  const [exportNotice, setExportNotice] = useState("");
  const [editingBulletId, setEditingBulletId] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState("");
  const [intelWarning, setIntelWarning] = useState("");
  const [resumeMode, setResumeMode] = useState<"master" | "upload" | "paste" | null>(null);
  const [modeTouched, setModeTouched] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [forceResumeSource, setForceResumeSource] = useState(false);
  const [autoBindState, setAutoBindState] = useState<"idle" | "running" | "failed">("idle");
  const autoBindMissionRef = useRef<string | null>(null);
  const [forceResumeStep, setForceResumeStep] = useState<null | "selection" | "strategy" | "target">(null);
  const [updateMasterResume, setUpdateMasterResume] = useState(false);
  const [masterImpactLabel, setMasterImpactLabel] = useState("");
  const [boundNeedsConfirm, setBoundNeedsConfirm] = useState(false);
  const [recoverDraftClaimId, setRecoverDraftClaimId] = useState<string | null>(null);
  const [recoverDraftText, setRecoverDraftText] = useState("");
  const [activeActionId, setActiveActionId] = useState<string | null>(null);
  const [actionDraftText, setActionDraftText] = useState("");
  const [outcomeMessage, setOutcomeMessage] = useState("");
  const [jdPaste, setJdPaste] = useState("");
  const [debug, setDebug] = useState(false);
  const forceResumeSourceRef = useRef(false);
  const optimizationSyncRef = useRef(false);

  useEffect(() => {
    forceResumeSourceRef.current = forceResumeSource;
  }, [forceResumeSource]);

  const refresh = useCallback(async (opts?: { preserveError?: boolean; quiet?: boolean }) => {
    if (!opts?.quiet) {
      setLoading(true);
    }
    if (!opts?.preserveError) {
      setError("");
    }
    try {
      const loaded = await readMission(missionId);
      setMission(loaded);
      const boundProfileId = (loaded.resume_source as { bound_profile_id?: string } | null)?.bound_profile_id || loaded.profile_id;
      const [nextResumes, nextSelection, nextProfile] = await Promise.all([
        readTargetResumes(missionId).catch(() => []),
        readExperienceSelection(missionId).catch(() => []),
        readProfile(boundProfileId).catch(() => null),
      ]);
      setResumes(nextResumes);
      setExperienceSelection(nextSelection);
      setSourceProfile(nextProfile);
      setExperiences(nextProfile?.experiences ?? []);
      if (!opts?.quiet) setLoading(false);
      void Promise.all([
        readReadiness(missionId).catch(() => null),
        readRedTeam(missionId).then((r) => normalizeRedTeamReport(r)).catch(() => null),
        readInterviewPack(missionId).catch(() => ({ topics: [] })),
        readMissionProofSnapshot(missionId).catch(() => null),
        readProofState(missionId).catch(() => null),
      ]).then(([nextReadiness, nextRedTeam, nextPack, nextProofSnap, nextProof]) => {
        setReadiness(nextReadiness);
        setRedTeam((prev) => (nextRedTeam ? nextRedTeam : isRedTeamExecuted(prev) ? prev : { findings: [] }));
        setRedTeamSettled(true);
        setInterviewPack(nextPack);
        setLastMockDebrief(resolveLastMockDebrief(missionId, nextProofSnap?.latest_completed_session ?? nextProofSnap?.session ?? null));
        setInterviewSessionStatus(nextProofSnap?.session?.status ?? nextProofSnap?.latest_completed_session?.status ?? null);
        setProof(nextProof);
      });
      const warnings = Array.isArray(loaded.warnings) ? loaded.warnings : [];
      if (!loaded.interview_intel?.length || warnings.includes("company_intel_unavailable")) {
        setIntelWarning("公司面试情报暂时没有成功加载。我们会先根据岗位 JD 继续分析。");
      } else {
        setIntelWarning("");
      }
      // While user is mid change-resume-source, do not clobber upload/paste selection with bound master.
      if (loaded.resume_source?.mode && !forceResumeSourceRef.current) {
        setResumeMode(loaded.resume_source.mode);
        setModeTouched(true);
      }
    } catch (caught) {
      if (!opts?.preserveError) {
        setError(humanizeMissionError(caught instanceof Error ? caught.message : "", "generic"));
      }
    } finally {
      // Essential mission/resume data controls the loading shell; optional proof
      // reads settle independently so slow proof cannot blank the resume tab.
      if (!opts?.quiet) setLoading(false);
    }
  }, [missionId]);

  useEffect(() => {
    setDebug(isDebugMode());
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (currentTab !== "role" || !mission?.target_job_id) return;
    let active = true;
    setTargetJob(null);
    setTargetJobError(false);
    void readTargetJob(mission.target_job_id, MISSION_API_BASE_URL)
      .then((job) => { if (active) setTargetJob(job); })
      .catch(() => { if (active) setTargetJobError(true); });
    return () => { active = false; };
  }, [currentTab, mission?.target_job_id]);

  useEffect(() => {
    if (currentTab !== "proof") return;
    markProofVisited(missionId);
  }, [currentTab, missionId]);

  // The ordinary resume path is AI-first: once a source is bound, generate the
  // selection, strategy, and target rewrite without making the user walk three
  // internal workflow pages. The user still edits decisions and bullets before
  // confirming the final resume.
  useEffect(() => {
    if (!mission || currentTab !== "resume" || forceResumeSource || boundNeedsConfirm || loading || busy || optimizationError || optimizationSyncRef.current) return;
    const boundId = boundProfileIdOf(mission);
    if (boundId && (sourceProfile?.profile_id !== boundId || sourceProfile.status !== "CONFIRMED")) return;
    const currentResumeStep = forceResumeSource ? "source" : (forceResumeStep ?? deriveResumeSubstep(normalizeWorkflowState(mission.workflow_state)));
    if (!mission.resume_source?.mode || currentResumeStep === "source") return;
    const state = normalizeWorkflowState(mission.workflow_state);
    const hasSelection = experienceSelection.length > 0;
    const hasResumeStrategy = Boolean(mission.resume_strategy && Object.keys(mission.resume_strategy).length);
    const hasTargetDraft = resumes.length > 0;
    const shouldGenerateSelection = !hasSelection && ["RESUME_SELECTED", "EXPERIENCE_SELECTION_REQUIRED"].includes(state);
    const shouldConfirmSelection = hasSelection && ["RESUME_SELECTED", "EXPERIENCE_SELECTION_REQUIRED"].includes(state);
    const shouldGenerateStrategy = hasSelection && !hasResumeStrategy && ["EXPERIENCES_CONFIRMED", "RESUME_STRATEGY_REQUIRED"].includes(state);
    const shouldConfirmStrategy = hasResumeStrategy && ["RESUME_STRATEGY_REQUIRED", "EXPERIENCES_CONFIRMED"].includes(state);
    const shouldGenerateTarget = hasResumeStrategy && !hasTargetDraft && ["RESUME_STRATEGY_CONFIRMED", "TARGET_RESUME_DRAFT"].includes(state);
    if (!shouldGenerateSelection && !shouldConfirmSelection && !shouldGenerateStrategy && !shouldConfirmStrategy && !shouldGenerateTarget) return;
    optimizationSyncRef.current = true;
    void (async () => {
      try {
        setBusy(true);
        if (shouldGenerateSelection) {
          setOptimizationStage(0);
          await withTaskTimeout(generateMissionStep(missionId, "experience-selection/generate"), 180_000, "经历整理");
          // The AI-first resume page should not stop after creating the
          // selection draft. Continue the same transition through strategy
          // confirmation and target-resume generation. Previously this effect
          // refreshed once, cleared its ref, and then returned without a
          // dependency change, leaving the right column on "正在生成逐条改写…".
          const generatedSelection = await readExperienceSelection(missionId);
          await saveExperienceSelection(missionId, generatedSelection, undefined, undefined, true);
          setOptimizationStage(1);
          await withTaskTimeout(generateMissionStep(missionId, "resume-strategy"), 180_000, "岗位策略生成");
          await confirmStrategy(missionId);
          setOptimizationStage(2);
          await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成");
        } else if (shouldConfirmSelection) {
          setOptimizationStage(0);
          await saveExperienceSelection(missionId, experienceSelection, undefined, undefined, true);
          setOptimizationStage(1);
          await withTaskTimeout(generateMissionStep(missionId, "resume-strategy"), 180_000, "岗位策略生成");
          await confirmStrategy(missionId);
          setOptimizationStage(2);
          await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成");
        } else if (shouldGenerateStrategy) {
          setOptimizationStage(1);
          await withTaskTimeout(generateMissionStep(missionId, "resume-strategy"), 180_000, "岗位策略生成");
          await confirmStrategy(missionId);
          setOptimizationStage(2);
          await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成");
        } else if (shouldConfirmStrategy) {
          setOptimizationStage(1);
          await confirmStrategy(missionId);
          setOptimizationStage(2);
          await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成");
        } else if (shouldGenerateTarget) {
          // RESUME_STRATEGY_CONFIRMED is already persisted. Calling the
          // confirmation endpoint again added an avoidable round trip (and
          // sometimes a 409) before the target resume request.
          if (state === "RESUME_STRATEGY_REQUIRED" || state === "EXPERIENCES_CONFIRMED") {
            await confirmStrategy(missionId);
          }
          setOptimizationStage(2);
          await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成");
        }
        await refresh({ quiet: true });
        setOptimizationStage(null);
      } catch (caught) {
        setRegenerationFailed(false);
        setOptimizationError(humanizeMissionError(caught instanceof Error ? caught.message : "", "generic"));
      } finally {
        optimizationSyncRef.current = false;
        setBusy(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mission?.id, mission?.workflow_state, mission?.resume_strategy, mission?.resume_source, sourceProfile?.profile_id, sourceProfile?.status, currentTab, forceResumeStep, experienceSelection.length, resumes.length, boundNeedsConfirm, forceResumeSource, loading, busy, optimizationError]);

useEffect(() => {
    // Intentionally no auto-replace from role/overview.
    // Sidebar and deep links must allow /role (company rematch) and read-only overview
    // even when workflow_state is past ROLE_UNDERSTOOD (e.g. RESUME_STRATEGY_REQUIRED).
    // CTA handlers still call nextRoute(...) after mutations.
  }, [mission, currentTab, missionId, router]);

  async function run(
    action: () => Promise<unknown>,
    kind: "generic" | "jd_analysis" | "company_intel" | "resume_parse" | "resume_ingest" | "resume_bind" | "experience_selection" = "generic",
  ) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (caught) {
      setError(humanizeMissionError(caught instanceof Error ? caught.message : "", kind));
    } finally {
      setBusy(false);
    }
  }

  async function updateDecision(selectionId: string, decision: ExperienceSelection["decision"]) {
    const target = experienceSelection.find((item) => item.id === selectionId);
    const next = experienceSelection.map((item) => {
      if (item.id !== selectionId) return item;
      const exp = experiences.find((row) => row.id === item.experience_id);
      const label = (exp?.title || "").trim() || "这段经历";
      return { ...item, decision, why: alignedExperienceWhy(decision, item.why, label) };
    });
    setExperienceSelection(next);
    setSavingDecision(true);
    setError("");
    try {
      setExperienceSelection(await saveExperienceSelection(missionId, next));
      // Keep rewrites in sync with decisions: when an experience becomes
      // 重点展示/保留 but has no rewrite bullet yet, regenerate the target
      // resume so the rewrite column always covers highlighted experiences.
      const keptDecision = decision === "KEEP_AND_HIGHLIGHT" || decision === "KEEP";
      const hadRewrite = target ? (latestResume?.bullets ?? []).some((bullet) => bullet.source_experience_id === target.experience_id) : false;
      if (keptDecision && !hadRewrite) {
        setSavingDecision(false);
        await run(async () => {
          await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成");
          await refresh();
        });
        return;
      }
    } catch (caught) {
      setError(humanizeMissionError(caught instanceof Error ? caught.message : "", "generic"));
      await refresh();
    } finally {
      setSavingDecision(false);
    }
  }

  const experienceMap = useMemo(() => {
    const map = new Map<string, ProfileExperience>();
    for (const item of experiences) map.set(item.id, item);
    return map;
  }, [experiences]);

  if (loading && !mission) {
    return (
      <main className="mission-shell">
        <div className="workflow-loading" role="status">
          <span className="loading-indicator" aria-hidden="true" />
          <p>正在打开岗位准备…</p>
        </div>
      </main>
    );
  }
  if (!mission) {
    return (
      <main className="mission-shell">
        <div className="workflow-error-state">
          <p className="message error" role="alert">
            {error || "岗位准备不存在。"}
          </p>
          <Link className="button-secondary" href="/missions">
            返回我的岗位
          </Link>
        </div>
      </main>
    );
  }

  const currentMission = mission;
  const what = currentMission.what_matters ?? {};
  // 后端在岗位解析软失败时仍会建任务（渐进式降级），这里据此给可恢复入口。
  const analysisDegradation = describeJdAnalysisDegradation({
    analysisError: currentMission.analysis_error,
    warnings: currentMission.warnings,
    whatMatters: what,
  });
  const latestResume = resumes[resumes.length - 1] ?? null;
  const highRiskCount = countHighRiskFindings(redTeam.findings);
  const workflowState = normalizeWorkflowState(currentMission.workflow_state);


  const resumeBound = Boolean(currentMission.resume_source?.mode);
  const decisionProgress = resumeDecisionProgress(latestResume?.bullets ?? []);
  const bulletsDecided = decisionProgress.total > 0 && decisionProgress.decided === decisionProgress.total;
  const targetConfirmed =
    ["TARGET_RESUME_CONFIRMED", "STRESS_TEST_REQUIRED", "STRENGTHENING_REQUIRED", "PROOF_IN_PROGRESS", "INTERVIEW_PREP_READY", "INTERVIEW_IN_PROGRESS", "INTERVIEW_DEBRIEF_READY", "OUTCOME"].includes(workflowState) ||
    (latestResume?.status === "CONFIRMED");
  const hasStrategy = Boolean(currentMission.resume_strategy && Object.keys(currentMission.resume_strategy).length > 0);
  const resumeStep = forceResumeSource ? "source" : (forceResumeStep ?? deriveResumeSubstep(workflowState));

  // 用户诉求：简历中心上传过一次简历后，进入岗位直接用这份简历开始优化，
  // 不再每次都弹「选择简历来源」。仅在无可用简历或自动绑定失败时回退到手动选择。
  useEffect(() => {
    if (currentTab !== "resume" || loading || busy || !mission) return;
    if (forceResumeSource || boundNeedsConfirm) return;
    if (resumeStep !== "source" || currentMission.resume_source?.mode) return;
    if (autoBindMissionRef.current === mission.id) return;
    autoBindMissionRef.current = mission.id;
    setAutoBindState("running");
    void bindResume("master");
    // bindResume 内部自带错误处理；结束后由下面的对账 effect 决定回退到手动选择还是继续。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTab, loading, busy, mission?.id, resumeStep, forceResumeSource, boundNeedsConfirm, currentMission.resume_source?.mode]);

  // 自动绑定对账：busy 结束后若来源仍未绑定 → 标记失败，回退到手动选择界面。
  useEffect(() => {
    if (autoBindState !== "running" || busy || loading) return;
    if (currentMission.resume_source?.mode) {
      setAutoBindState("idle");
    } else {
      setAutoBindState("failed");
    }
  }, [autoBindState, busy, loading, currentMission.resume_source?.mode]);

  const intel = summarizeIntelCoverage(currentMission.interview_intel ?? []);
  const intelLayers = partitionIntelBySource(currentMission.interview_intel ?? []);
  const companyPending = isUnknownIdentity(currentMission.company);
  const redTeamExecuted = isRedTeamExecuted(redTeam);
  const evidenceGapCount = parseEvidenceGapCount(readiness);
  const interviewableClaimsOk = hasInterviewableClaim(proof?.claims ?? []);
  const redTeamLoading = !redTeamSettled;
  const visitedProof = hasVisitedProofForMission(missionId, workflowState);
  const interviewGateInput = {
    targetConfirmed,
    redTeamExecuted,
    redTeamLoading,
    readinessStatus: readiness?.status,
    highRiskCount,
    hasInterviewPack: interviewPack.topics.length > 0,
    evidenceGapCount,
    workflowState,
    hasInterviewableClaim: interviewableClaimsOk,
    hasVisitedProof: visitedProof,
  };
  const interviewCta = resolveInterviewTabCta(interviewGateInput);
  const proofNextStep = resolveProofNextStep({
    targetConfirmed,
    readinessStatus: readiness?.status,
    claims: proof?.claims ?? [],
    proofActions: proof?.proof_actions ?? [],
  });
  const compactHints = buildInterviewTabCompactHints({
    company: currentMission.company,
    resumeSourceMode: currentMission.resume_source?.mode,
    targetConfirmed,
    redTeamExecuted,
    redTeamLoading,
    highRiskCount,
    readinessStatus: readiness?.status,
    workflowState,
    hasInterviewPack: interviewPack.topics.length > 0,
    evidenceGapCount,
    hasInterviewableClaim: interviewableClaimsOk,
    coreMode: true,
  });
  const ctaContext = {
    company: currentMission.company,
    hasStrategy,
    hasSelection: experienceSelection.length > 0,
    hasTargetResume: Boolean(latestResume),
    bulletsDecided,
    targetConfirmed,
    highRiskCount,
    hasInterviewPack: interviewPack.topics.length > 0,
    modeSelected: Boolean(resumeMode),
    redTeamExecuted,
    readinessStatus: readiness?.status ?? null,
    evidenceGapCount,
  };

  /** 岗位解析降级后的唯一恢复动作：拿原始 JD 再跑一次解析。 */
  async function reanalyzeRole() {
    const raw = (targetJob?.raw_text || "").trim();
    if (raw.length < 20) {
      setError("原始 JD 还没读到（或过短），请刷新页面后再试。");
      return;
    }
    await run(async () => {
      await withTaskTimeout(reanalyzeMission(missionId, raw), 120_000, "岗位识别");
    }, "jd_analysis");
  }

  /** Open 补强 (proof) tab. Skip advance(strengthen) when already STRENGTHENING_* — that 409s and blocks navigation. */
  async function navigateToStrengthen() {
    markProofVisited(missionId);
    await run(async () => {
      if (canAdvanceStrengthenEvent(workflowState)) {
        await advanceMission(missionId, "strengthen");
      }
      router.push(missionHref(missionId, "proof"));
    });
  }

  function experienceLabel(experienceId: string) {
    const item = experienceMap.get(experienceId);
    if (!item) return { title: missingExperienceLabel(), meta: "" };
    return {
      title: item.title?.trim() || "未命名经历",
      meta: [item.organization, item.dates].filter(Boolean).join(" · "),
    };
  }

  async function bindResume(forcedMode?: "master" | "upload" | "paste") {
    const mode = forcedMode ?? resumeMode;
    if (!mode) throw new Error("请先选择简历来源。");
    let errorKind: "resume_ingest" | "resume_bind" | "experience_selection" = "resume_ingest";
    setBusy(true);
    setError("");
    setResumeParseStage(0);
    try {
      if (mode === "master") {
        const profile = await readProfile(currentMission.profile_id);
        if (!profile.experiences.length) {
          throw new Error("当前档案还没有经历，请上传或粘贴简历。");
        }
        if (looksLikePlaceholderResume(profile)) {
          throw new Error("当前简历包含占位内容。请上传真实 PDF 或粘贴简历文本后继续。");
        }
        errorKind = "resume_bind";
        await confirmResumeSource(missionId, "master");
        setForceResumeSource(false);
        setUpdateMasterResume(false);
      } else if (resumeMode === "upload") {
        if (!uploadFile) throw new Error("请先选择 PDF 简历。");
        if (uploadFile.size > 10 * 1024 * 1024) throw new Error("这份 PDF 超过 10MB，压缩后再上传，或改用「粘贴文本」。");
        if (updateMasterResume) {
          const impact = await readMasterResumeImpact(currentMission.profile_id).catch(() => null);
          const affected = (impact?.missions || []).filter((item) => item.affected_by_master_update !== false && item.id !== missionId);
          if (affected.length) {
            const names = affected
              .slice(0, 5)
              .map((item) => item.display_name || [item.company, item.role].filter(Boolean).join(" · ") || item.id.slice(0, 8))
              .join("、");
            const extra = affected.length > 5 ? ` 等 ${affected.length} 个岗位` : "";
            const ok = window.confirm(
              `这份简历也用于其他岗位。更新后可能影响这些岗位：${names}${extra}。

确定要更新已有简历档案吗？`,
            );
            if (!ok) return;
          } else {
            const ok = window.confirm("这份简历也用于其他岗位。更新后相关岗位会看到新经历。确定继续？");
            if (!ok) return;
          }
        }
        const bound = await withTaskTimeout(bindMissionResumePdf(missionId, uploadFile, { updateMaster: updateMasterResume }), 180_000, "简历解析");
        upsertProfileLabelFromFilename(
          updateMasterResume ? currentMission.profile_id : bound.bound_profile_id || currentMission.profile_id,
          uploadFile.name,
        );
        if (!bound.experiences.length) {
          throw new Error("未能从 PDF 提取到经历。若是扫描件或图片型 PDF，请改用「粘贴文本」。");
        }
        if (!updateMasterResume && bound.isolation !== "mission_local") {
          throw new Error("上传未能生成本岗位专用档案，请重试上传，或改用「粘贴文本」。");
        }
        if (looksLikePlaceholderResume({ experiences: bound.experiences as ProfileExperience[] })) {
          throw new Error("这份 PDF 解析结果像占位模板（XX 公司 / 文职助理），不是可用的真实经历。请换一份真实简历 PDF，或改用「粘贴文本」。");
        }
        // Apply bind payload immediately so UI leaves 正在上传/解析… / source step while
        // experience-selection generate + refresh still run under busy=true.
        if (bound.mission) {
          setMission(bound.mission);
        }
        if (Array.isArray(bound.experiences) && bound.experiences.length) {
          setExperiences(bound.experiences as ProfileExperience[]);
        }
        setForceResumeSource(false);
        setUpdateMasterResume(false);
      } else {
        if (pasteText.trim().length < 40) throw new Error("粘贴的简历文本太短。");
        if (updateMasterResume) {
          const ok = window.confirm("这份简历也用于其他岗位。更新后相关岗位会看到新经历。确定继续？");
          if (!ok) return;
        }
        const bound = await withTaskTimeout(bindMissionResumeText(missionId, pasteText.trim(), { updateMaster: updateMasterResume }), 180_000, "简历解析");
        if (!bound.experiences.length) {
          throw new Error("未能从文本提取到经历，请检查粘贴内容后重试。");
        }
        if (!updateMasterResume && bound.isolation !== "mission_local") {
          throw new Error("粘贴未能生成本岗位专用档案，请重试，或改用「上传 PDF」。");
        }
        if (looksLikePlaceholderResume({ experiences: bound.experiences as ProfileExperience[] })) {
          throw new Error("粘贴内容解析结果像占位模板（XX 公司 / 文职助理）。请粘贴真实简历全文后再试。");
        }
        if (bound.mission) {
          setMission(bound.mission);
        }
        if (Array.isArray(bound.experiences) && bound.experiences.length) {
          setExperiences(bound.experiences as ProfileExperience[]);
        }
        setForceResumeSource(false);
        setUpdateMasterResume(false);
      }
      errorKind = "experience_selection";
      setResumeParseStage(1);
      // Auto-generate selection draft if empty — stay on EXPERIENCE_SELECTION_REQUIRED until user confirms
      const selection = await readExperienceSelection(missionId).catch(() => []);
      setResumeParseStage(2);
      if (!selection.length) {
        await withTaskTimeout(generateMissionStep(missionId, "experience-selection/generate"), 180_000, "经历整理");
      }
      await refresh();
      setResumeParseStage(null);
    } catch (caught) {
      const message = humanizeMissionError(caught instanceof Error ? caught.message : "", errorKind);
      setError(message);
      // Keep upload/paste selection + forceResumeSource on failure. refresh() used to clear error
      // and reset resumeMode from resume_source.mode (often master), which looked like Processing then bounce.
      if (errorKind === "experience_selection") {
        // Confirm already persisted; soft-sync mission without wiping the visible error or source UI.
        try {
          await refresh({ preserveError: true, quiet: true });
        } catch {
          /* ignore secondary refresh errors */
        }
      }
    } finally {
      setBusy(false);
    }
  }

  async function advanceResume() {
    if (resumeStep === "source" || workflowState === "RESUME_REQUIRED") {
      await bindResume();
      return;
    }
    if (resumeStep === "selection") {
      await run(async () => {
        if (!experienceSelection.length) {
          await generateMissionStep(missionId, "experience-selection/generate");
          return; // stay until user confirms
        }
        setForceResumeStep(null);
        // User Primary CTA = confirm decisions (advances workflow); chip edits save without confirm
        await saveExperienceSelection(missionId, experienceSelection, undefined, undefined, true);
        // Continuity: after confirm, draft strategy so user is not stuck on empty RESUME_STRATEGY_REQUIRED.
        await generateMissionStep(missionId, "resume-strategy");
      });
      return;
    }
    if (resumeStep === "strategy") {
      await run(async () => {
        if (!hasStrategy) {
          await generateMissionStep(missionId, "resume-strategy");
          return; // show strategy; wait for next click
        }
        await confirmStrategy(missionId);
        await generateMissionStep(missionId, "target-resumes");
      });
      return;
    }
    if (resumeStep === "target" || workflowState === "TARGET_RESUME_DRAFT" || workflowState === "TARGET_RESUME_CONFIRMED") {
      if (workflowState === "TARGET_RESUME_DRAFT" || (latestResume && !targetConfirmed)) {
        if (!bulletsDecided) {
          setError(`请先处理所有改写，当前已处理 ${decisionProgress.decided} / ${decisionProgress.total} 项。`);
          return;
        }
        await run(async () => {
          await confirmTargetResume(missionId);
        });
        return;
      }
      // A confirmed resume is the hand-off point to the mock interview. Red-team
      // remains a backend/debug capability and is not a user-facing gate.
      router.push(missionHref(missionId, "interview"));
      return;
    }
    if (resumeStep === "stress" || resumeStep === "strengthen") {
      router.push(missionHref(missionId, "interview"));
      return;
    }
    router.push(nextRoute(workflowState, missionId) as never);
  }



  async function exportTargetResumePdf() {
    if (!latestResume || !currentMission) return;
    setError("");
    setExportNotice("");
    let profileSnap: Awaited<ReturnType<typeof readProfile>> | null = null;
    try {
      const resolved = resolveExportProfileId(currentMission);
      profileSnap = resolved.profileId ? await readProfile(resolved.profileId) : null;
    } catch {
      profileSnap = null;
    }
    const knownExpIds = (experiences.length ? experiences : profileSnap?.experiences ?? [])
      .map((exp) => String(exp.id))
      .filter(Boolean);
    if (countExportableBullets(latestResume, knownExpIds) === 0) {
      const empty = exportEmptyContentFeedback();
      setError(empty.message);
      setExportNotice("");
      return;
    }
    // 联系方式以简历工作台（Studio 投递版）为单一事实来源；这里只检查岗位内容，
    // 避免「Studio 已填联系方式、来源档案没填」导致假阳性提醒。
    const checks = buildPreExportChecklist({
      profile: profileSnap,
      experiences: experiences.length ? experiences : profileSnap?.experiences ?? [],
      bullets: latestResume.bullets,
      selections: experienceSelection.map((row) => ({ experience_id: row.experience_id, decision: row.decision })),
      includeContactWarnings: false,
    });
    const blocking = checks.filter((item) => item.level === "block");
    if (blocking.length) {
      setError(blocking.map((item) => item.message).join("\n"));
      return;
    }
    const warnings = checks.filter((item) => item.level === "warn");
    if (warnings.length) {
      setExportNotice(`导出前检查：${warnings.map((item) => item.message).join("；")}`);
    }
    const html = buildTargetResumeExportHtml({
      company: currentMission.company,
      role: currentMission.role,
      seniority: currentMission.seniority,
      targetResume: latestResume,
      profile: profileSnap,
      experiences: experiences.length ? experiences : profileSnap?.experiences ?? [],
      selections: experienceSelection.map((row) => ({ experience_id: row.experience_id, decision: row.decision })),
    });
    const win = window.open("", "_blank");
    const feedback = exportPrintWindowFeedback(Boolean(win));
    if (feedback.tone === "error") {
      setError(feedback.message);
      setExportNotice("");
      return;
    }
    win!.document.write(html);
    win!.document.close();
    const filename = buildExportFileName({ name: profileSnap?.full_name || profileSnap?.name, company: currentMission.company, role: currentMission.role, extension: "pdf" });
    const warningText = warnings.length ? ` 导出前检查：${warnings.map((item) => item.message).join("；")}` : "";
    setExportNotice(`${feedback.message} 建议文件名：${filename}${warningText}`);
  }

  function renderRole() {
    const capabilities = listOf(what.core_capabilities)
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object") {
          const row = item as { label?: unknown; name?: unknown; capability?: unknown };
          return textOf(row.label ?? row.name ?? row.capability);
        }
        return "";
      })
      .filter(Boolean)
      .slice(0, 4);

    return (
      <>
        <div className="mission-heading mission-heading-compact">
          <div>
            <p className="eyebrow">岗位档案</p>
            <h2>确认岗位信息</h2>
            <p className="summary">核对识别结果，再选择简历来源。</p>
          </div>
        </div>

        {analysisDegradation.degraded && (
          <section className="mission-card mission-analysis-fallback" role="status">
            <p className="section-kicker">下一步只有一个动作</p>
            <h3>岗位智能解析没跑完</h3>
            <p className="summary">{analysisDegradation.message}</p>
            <div className="mission-action-row">
              <PrimaryButton disabled={busy || !(targetJob?.raw_text || "").trim()} onClick={() => void reanalyzeRole()}>
                {busy ? "正在重新解析…" : "重新解析岗位"}
              </PrimaryButton>
              <span className="mission-analysis-fallback-hint">或者直接在下面手动更正公司 / 岗位，再「保存岗位」。</span>
            </div>
          </section>
        )}

        <section className="mission-card">
          <p className="section-kicker">{analysisDegradation.degraded ? "岗位基本信息" : "岗位已识别"}</p>
          <h3>
            {isUnknownIdentity(currentMission.company)
              ? "请补充公司和岗位名称"
              : "已识别：" + String(currentMission.company) + " / " + String(currentMission.role)}
          </h3>
          <p className="summary">
            {capabilities.length
              ? `这个岗位主要关注：${capabilities.join("、")}。`
              : "还没有解析出这个岗位的关键关注点——重新解析，或直接在下面手动更正岗位信息。"}
          </p>
          <div className="mission-original-jd">
            <p className="section-kicker">原始岗位描述</p>
            {targetJob?.raw_text ? <div className="mission-original-jd-text">{targetJob.raw_text}</div> : <p className="summary">{targetJobError ? "原始岗位描述暂时无法读取，请刷新页面重试。" : "正在读取原始岗位描述…"}</p>}
          </div>
        </section>

        <MissionMatchCard missionId={missionId} />

        <BossKitPanel missionId={missionId} />

        <form
          key="mission-identity"
          className="mission-card mission-identity-form"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            void run(async () => {
              await updateMissionIdentity(currentMission.id, {
                company: identityInputValue(String(form.get("company") || "")) || "UNKNOWN",
                role: identityInputValue(String(form.get("role") || "")) || "UNKNOWN",
                role_family: identityInputValue(String(form.get("role_family") || currentMission.role_family || "")) || "UNKNOWN",
                seniority: identityInputValue(String(form.get("seniority") || "")) || "UNKNOWN",
                location: identityInputValue(String(form.get("location") || "")) || null,
              });
            });
          }}
        >
          <div className="section-heading">
            <div>
              <p className="section-kicker">需要更正时再编辑</p>
              <h3>公司 / 岗位</h3>
            </div>
          </div>
          <div className="mission-identity-grid">
            <label className="field-label">
              公司
              <input name="company" defaultValue={identityInputValue(currentMission.company)} placeholder="例如：百度" />
            </label>
            <label className="field-label">
              岗位
              <input name="role" defaultValue={identityInputValue(currentMission.role)} placeholder="例如：AI 产品经理" />
            </label>
            <label className="field-label">
              级别
              <input name="seniority" defaultValue={seniorityLabel(currentMission.seniority)} placeholder="校招 / 实习" />
            </label>
            <label className="field-label">
              地点
              <input name="location" defaultValue={locationLabel(currentMission.location)} placeholder="可选" />
            </label>
          </div>
          <button type="submit" className="button-secondary" disabled={busy}>保存岗位</button>
        </form>

        <section className="mission-card">
          <p className="section-kicker">下一步</p>
          <h3>简历准备</h3>
          <p className="summary">自动使用你在简历中心上传的简历，进入优化流程——无需重复上传。</p>
          <PrimaryButton
            disabled={busy}
            onClick={() => {
              const roleStates = new Set(["JD_REQUIRED", "JOB_ANALYZING", "ROLE_UNDERSTOOD"]);
              if (roleStates.has(workflowState)) {
                void run(async () => {
                  await advanceMission(missionId, "select_resume");
                  router.push(missionHref(missionId, "resume"));
                });
                return;
              }
              router.push(nextRoute(workflowState, missionId));
            }}
          >
            开始简历优化
          </PrimaryButton>
        </section>
      </>
    );
  }

  function renderResumeSource() {
    // 正常流程：简历中心上传过简历 → 自动绑定，不再让用户每次三选一。
    // 只有自动绑定失败（无简历/解析失败）或用户主动「更换简历来源」才显示完整选择器。
    const showChooser = forceResumeSource || autoBindState === "failed";
    return (
      <section className="mission-card">
        <p className="section-kicker">简历来源</p>
        <h3>{showChooser ? "选择简历来源" : "使用简历中心的简历"}</h3>
        <p className="summary">
          {showChooser
            ? "选择已有简历，或为当前岗位上传新版本。"
            : "将自动使用你在简历中心上传的简历，直接进入优化流程；想换简历可到「简历中心」更新，或在下面点「更换简历来源」。"}
        </p>
        {showChooser ? null : autoBindState === "running" ? (
          <p className="mission-pipeline-note" role="status">正在读取简历中心的简历并整理经历…</p>
        ) : (
          <p className="mission-pipeline-note">正在准备使用已有简历…</p>
        )}
        {showChooser && (
          <p className="mission-pipeline-note">
            当前已绑定：{resumeSourceLine(currentMission, experiences)}。
            重新选择后会回到经历筛选，可再走后续步骤。
            {forceResumeSource ? (
              <>
                {" "}
                <TextButton disabled={busy} onClick={() => setForceResumeSource(false)}>
                  取消更换
                </TextButton>
              </>
            ) : null}
          </p>
        )}
        {showChooser && (
        <>
        <div className="mission-resume-choices">
          <label className={resumeMode === "master" ? "proof-select-card selected" : "proof-select-card"}>
            <input type="radio" name="resume-mode" checked={resumeMode === "master"} onChange={() => { setResumeMode("master"); setModeTouched(true); }} />
            <span>
              <strong>已有简历</strong>
              {resumeMode === "master" ? <small>■ 已选择</small> : null}
              <small>
                使用已有简历中的真实经历。
              </small>
            </span>
          </label>
          <label className={resumeMode === "upload" ? "proof-select-card selected" : "proof-select-card"}>
            <input type="radio" name="resume-mode" checked={resumeMode === "upload"} onChange={() => { setResumeMode("upload"); setModeTouched(true); }} />
            <span>
              <strong>上传 PDF</strong>
              {resumeMode === "upload" ? <small>■ 已选择</small> : null}
              <small>作为当前岗位的简历来源。</small>
            </span>
          </label>
          <label className={resumeMode === "paste" ? "proof-select-card selected" : "proof-select-card"}>
            <input type="radio" name="resume-mode" checked={resumeMode === "paste"} onChange={() => { setResumeMode("paste"); setModeTouched(true); }} />
            <span>
              <strong>粘贴文本</strong>
              {resumeMode === "paste" ? <small>■ 已选择</small> : null}
              <small>粘贴完整简历内容。</small>
            </span>
          </label>
        </div>
        {resumeMode === "upload" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
            <input type="file" accept="application/pdf,.pdf" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
            {uploadFile ? (
              <small className="mission-pipeline-note">
                已选择：{uploadFile.name}（{(uploadFile.size / 1024).toFixed(0)} KB）
                {busy ? " · 正在上传/解析…" : ""}
              </small>
            ) : (
              <small className="mission-pipeline-note">请选择 PDF；选中后会显示文件名，再点下方继续。</small>
            )}
          </div>
        )}
        {resumeMode === "paste" && (
          <textarea rows={12} value={pasteText} onChange={(event) => setPasteText(event.target.value)} placeholder="粘贴简历全文…" />
        )}
        
        {(resumeMode === "upload" || resumeMode === "paste") && (
          <label className="mission-pipeline-note" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start" }}>
            <input
              type="checkbox"
              checked={updateMasterResume}
              disabled={busy}
              onChange={(event) => setUpdateMasterResume(event.target.checked)}
            />
            <span>
              <strong>同时更新已有简历档案</strong>
              <br />
              默认只用于当前岗位。勾选后，其他使用此档案的岗位也会受影响。
              {masterImpactLabel ? <><br />{masterImpactLabel}</> : null}
            </span>
          </label>
        )}

        <PrimaryButton disabled={busy || !modeTouched || !resumeMode || (resumeMode === "upload" && !uploadFile) || (resumeMode === "paste" && pasteText.trim().length < 40)} onClick={() => void advanceResume()}>
          {busy ? "正在读取简历…" : "使用这份简历"}
        </PrimaryButton>
        {!forceResumeSource ? (
          <p className="mission-pipeline-note">
            自动使用简历失败时，也可以先到
            <Link href="/resumes" className="app-link">简历中心</Link>
            确认简历已上传，再回来重试。
          </p>
        ) : null}
        </>
        )}
        {resumeParseStage !== null && <TaskProgress kind="resume-parse" activeIndex={resumeParseStage} error={!busy ? error : ""} onRetry={() => void bindResume(resumeMode ?? "master")} />}
        {confirmableProfileIdOf(currentMission) ? (
          <div style={{ marginTop: "1rem" }}>
            <MissionProfileConfirmCard
              boundProfileId={confirmableProfileIdOf(currentMission)!}
              busy={busy}
              onConfirmed={async () => {
                setBoundNeedsConfirm(false);
                setOptimizationError("");
                await refresh();
                await run(async () => {
                  await generateMissionStep(missionId, "claim-analysis");
                  await refresh({ quiet: true });
                });
              }}
              onNeedsConfirmChange={setBoundNeedsConfirm}
            />
          </div>
        ) : null}
      </section>
    );
  }

  function renderSourceResumeColumn() {
    const profile = sourceProfile;
    const education = profile?.education ?? [];
    const certifications = profile?.certifications ?? [];
    const skills = (profile?.skills ?? []).map((item) => typeof item === "string" ? item : item.name || "").filter(Boolean);
    const sectionOrder = (((currentMission.resume_source as Record<string, unknown> | null)?.section_order as string[] | undefined) ?? ["education", "honors", "project", "experience", "campus", "skills"]);
    const orderedSections = Array.from(new Set(sectionOrder.map((item) => String(item).toLowerCase())));
    const renderEducation = education.length ? (
      <div className="resume-source-section" key="education"><strong>教育背景</strong>{education.map((item, index) => <div className="resume-source-item" key={item.id || index}><strong>{item.institution || item.school || "教育经历"}</strong><small>{[item.degree, item.field_of_study || item.major, item.dates].filter(Boolean).join(" · ")}</small>{item.relevant_courses?.length ? <p>主修课程：{item.relevant_courses.join("、")}</p> : null}</div>)}</div>
    ) : null;
    const renderExperiences = (kind: "project" | "experience" | "campus") => {
      const rows = (experiences ?? []).filter((item) => {
        const type = String(item.experience_type || "").toUpperCase();
        if (kind === "project") return type.includes("PROJECT") || type.includes("RESEARCH") || type.includes("COMPETITION");
        if (kind === "campus") return type.includes("CAMPUS") || type.includes("STUDENT") || type.includes("LEADERSHIP") || /学生会|班委|心理委员|体育部|纪律委员/.test(`${item.title || ""}${item.description || ""}`);
        return !type.includes("PROJECT") && !type.includes("RESEARCH") && !type.includes("COMPETITION") && !type.includes("CAMPUS") && !type.includes("STUDENT") && !type.includes("LEADERSHIP");
      });
      if (!rows.length) return null;
      const heading = kind === "project" ? "主要科研及竞赛经历" : kind === "campus" ? "校园经历" : "实习与工作经历";
      return <div className="resume-source-section" key={kind}><strong>{heading}</strong>{rows.map((item) => (
        <div className={`resume-source-item ${highlightedExperienceId === item.id ? "is-linked" : ""}`} key={item.id} id={`resume-source-${item.id}`}>
          <strong>{item.title || "未命名经历"}</strong>
          <small>{[item.organization, item.dates].filter(Boolean).join(" · ")}</small>
          <p>{item.description || "原简历未填写具体描述。"}</p>
          <button type="button" className="mission-text-btn" onClick={() => {
            setHighlightedExperienceId(item.id);
            document.getElementById(`resume-rewrite-${item.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
          }}>查看对应改写</button>
        </div>
      ))}</div>;
    };
    const renderSkills = skills.length ? <div className="resume-source-section" key="skills"><strong>个人技能</strong><p>{skills.join("、")}</p></div> : null;
    const renderHonors = certifications.length ? <div className="resume-source-section" key="honors"><strong>荣誉与证书</strong>{certifications.map((item, index) => <div className="resume-source-item" key={item.id || index}><strong>{item.name || "证书/荣誉"}</strong><small>{[item.issuer, item.date, item.score].filter(Boolean).join(" · ")}</small></div>)}</div> : null;
    const sectionMap: Record<string, ReactNode> = {
      education: renderEducation,
      honors: renderHonors,
      certifications: renderHonors,
      project: renderExperiences("project"),
      research: renderExperiences("project"),
      experience: renderExperiences("experience"),
      work: renderExperiences("experience"),
      campus: renderExperiences("campus"),
      skills: renderSkills,
    };
    const sections = orderedSections.map((key) => sectionMap[key]).filter(Boolean);
    if (!sections.length) return <p className="mission-empty">正在读取原始简历内容…</p>;
    return <>{sections}</>;
  }

  function renderOptimizationWorkspace() {
    const guidance = listOf(currentMission.resume_strategy?.experience_guidance);
    const guidanceById = new Map(guidance.map((item) => [String(item.experience_id || ""), item]));
    const directionHighlight = guidance.flatMap((item) => listOf(item.what_to_highlight).map((value) => textOf(value))).filter(Boolean).slice(0, 4);
    const directionAvoid = guidance.flatMap((item) => listOf(item.what_to_avoid).map((value) => textOf(value))).filter(Boolean).slice(0, 3);
    const selectionByExperience = new Map(experienceSelection.map((item) => [item.experience_id, item]));
    const rewriteIds = new Set((latestResume?.bullets ?? []).map((bullet) => bullet.source_experience_id).filter(Boolean) as string[]);
    const regenerate = async () => {
      setBusy(true);
      setError("");
      setRegenerationFailed(false);
      try {
        setOptimizationStage(0);
        setOptimizationError("");
        await withTaskTimeout(regenerateResumeOptimization(missionId), 180_000, "岗位版本重新生成");
        // Regeneration is an explicit user action, so finish the complete
        // AI-first pipeline in this request instead of relying on a later
        // effect pass to notice the intermediate workflow state.
        const generatedSelection = await withTaskTimeout(readExperienceSelection(missionId), 180_000, "经历整理");
        await saveExperienceSelection(missionId, generatedSelection, undefined, undefined, true);
        setOptimizationStage(1);
        await withTaskTimeout(generateMissionStep(missionId, "resume-strategy"), 180_000, "岗位策略生成");
        await confirmStrategy(missionId);
        setOptimizationStage(2);
        await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成");
        await refresh();
        setOptimizationStage(null);
      } catch (caught) {
        setRegenerationFailed(true);
        setOptimizationError(humanizeMissionError(caught instanceof Error ? caught.message : "", "generic"));
      } finally {
        setBusy(false);
      }
    };
    return (
      <section className="mission-card">
        <div className="section-heading">
          <div>
            <p className="section-kicker">岗位定向版本</p>
            <h3>原始简历 / 岗位定向版本</h3>
            <p className="summary">基于岗位「{currentMission?.company || ""}{currentMission?.role ? ` · ${currentMission.role}` : ""}」对照原文审阅改写，并逐条决定是否采用。</p>
            {directionHighlight.length || directionAvoid.length ? <p className="mission-pipeline-note">调整重点：突出 {directionHighlight.join("、") || "与岗位相关的动作和结果"}；精简 {directionAvoid.join("、") || "无关细节"}。</p> : null}
          </div>
          <TextButton disabled={busy} onClick={() => void regenerate()}>重新生成岗位版本</TextButton>
        </div>
        {optimizationStage !== null && <TaskProgress kind="resume-optimize" activeIndex={optimizationStage} error={optimizationError} onRetry={() => { if (regenerationFailed) void regenerate(); else setOptimizationError(""); }} />}
        <p className="mission-pipeline-note" role="status">已处理 {decisionProgress.decided} / {decisionProgress.total} 项</p>
        <div className="resume-optimization-workspace">
          <div className="resume-optimization-column">
            <p className="section-kicker">原始简历</p>
            <h3>保留原文与原有结构</h3>
            {renderSourceResumeColumn()}
            {experienceSelection.length ? <div className="resume-source-section"><strong>经历筛选</strong>{dedupeExperienceSelections(experienceSelection, experienceMap).map((selection) => {
              const label = experienceLabel(selection.experience_id);
              return <div className="resume-source-item" key={selection.id}><strong>{label.title}</strong><span className="resume-decision-note">AI 建议：{selection.decision === "KEEP_AND_HIGHLIGHT" ? "重点优化" : selection.decision === "KEEP" ? "保留" : selection.decision === "DEEMPHASIZE" ? "弱化" : "暂不放入"}</span><WhyPoints text={stripEvidenceDump(selection.why)} /><div className="decision-chip-row">{EXPERIENCE_DECISION_OPTIONS.map((option) => <button key={option.value} type="button" className={selection.decision === option.value ? "decision-chip active" : "decision-chip"} disabled={savingDecision || busy} onClick={() => void updateDecision(selection.id, option.value)}>{option.label}</button>)}</div></div>;
            })}</div> : null}
          </div>
          <div className="resume-optimization-column">
            <p className="section-kicker">岗位定向版本</p>
            <h3>{latestResume ? `岗位版本 v${latestResume.version}` : "正在生成岗位版本…"}</h3>
            <div className="resume-mobile-source"><details><summary>查看完整原始简历</summary>{renderSourceResumeColumn()}</details></div>
            {!latestResume ? <p className="mission-empty">正在整理原始简历与岗位要求。</p> : null}
            {(latestResume?.bullets ?? []).map((bullet, bulletIndex) => {
              const guidanceItem = bullet.source_experience_id ? guidanceById.get(bullet.source_experience_id) : null;
              const needsTruthCheck = bullet.grounding_status === "NEEDS_CONFIRMATION" || bullet.grounding_status === "UNSUPPORTED";
              const isSyntheticProject = (bullet.risk_flags ?? []).some((flag) => String(flag).toUpperCase() === "SYNTHETIC_PROJECT");
              const isEditing = editingBulletId === bullet.id;
              const factConfirmed = (bullet.risk_flags ?? []).some((flag) => String(flag).toUpperCase() === "FACT_CONFIRMED");
              const sameExperienceBefore = (latestResume?.bullets ?? []).slice(0, bulletIndex).some((item) => item.source_experience_id === bullet.source_experience_id && Boolean(item.source_experience_id));
              const siblingAlreadyChosen = Boolean(bullet.source_experience_id && (latestResume?.bullets ?? []).some((item) => item.id !== bullet.id && item.source_experience_id === bullet.source_experience_id && (item.status === "ACCEPTED" || item.status === "EDITED")));
              const highlightText = listOf(guidanceItem?.what_to_highlight).map((value) => textOf(value)).filter(Boolean).join("、") || listOf(bullet.target_capabilities).map((value) => textOf(value)).filter(Boolean).join("、") || "项目中的个人动作、方案取舍和测试结果";
              const avoidText = listOf(guidanceItem?.what_to_avoid).map((value) => textOf(value)).filter(Boolean).join("、") || "无关的专业细节和未经验证的数字";
              const statusLabel = targetResumeBulletStatusLabel(bullet.status);
              return <article id={!sameExperienceBefore && bullet.source_experience_id ? `resume-rewrite-${bullet.source_experience_id}` : undefined} className={`resume-ai-item ${statusLabel === "已接受" ? "resume-ai-item-accepted" : statusLabel === "未采用" ? "resume-ai-item-rejected" : ""}`} key={bullet.id} onMouseEnter={() => setHighlightedExperienceId(bullet.source_experience_id)} onMouseLeave={() => setHighlightedExperienceId(null)} onFocus={() => setHighlightedExperienceId(bullet.source_experience_id)}>{!sameExperienceBefore ? <div><h4>{isSyntheticProject ? (bullet.project_title || "项目草案") : experienceLabel(bullet.source_experience_id || "").title}</h4>{!isSyntheticProject && experienceLabel(bullet.source_experience_id || "").meta ? <p className="resume-project-meta">{experienceLabel(bullet.source_experience_id || "").meta}</p> : null}</div> : <p className="resume-bullet-group-label">同一经历的下一条改写（只能选择一条）</p>}<div className="resume-original">原文：{bullet.original_text || "—"}</div>{isEditing ? <textarea className="textarea mission-bullet-edit-textarea" rows={5} value={editingDraft} disabled={busy} onChange={(event) => setEditingDraft(event.target.value)} /> : <div className="resume-rewrite">建议改写：<StructuredRewrite text={targetResumeBulletDisplayText(bullet)} /></div>}<div className="resume-ai-reason">改写说明：{bullet.reason || "把原始事实改写成更容易被招聘方理解的岗位语言。"}</div><div className="resume-ai-reason">调整重点：强化 {highlightText}；弱化 {avoidText}。</div>{siblingAlreadyChosen && statusLabel !== "已接受" && statusLabel !== "已编辑" ? <div className="resume-fact-warning">同一经历已有选定改写。采用此版本时将自动替换。</div> : null}{isSyntheticProject ? <div className="resume-fact-warning">建议完成的作品集项目 · 尚未写入正式简历。完成并确认事实后才能采用。</div> : null}{needsTruthCheck ? <div className="resume-fact-warning">此处含原始简历未明确提供的信息，请先确认事实。</div> : null}{statusLabel ? <span className={`mission-bullet-badge mission-bullet-badge-${statusLabel === "已接受" ? "accepted" : statusLabel === "未采用" ? "rejected" : "edited"}`}>{statusLabel}</span> : null}<div className="mission-bullet-actions">{(needsTruthCheck || isSyntheticProject) && !factConfirmed ? <TextButton disabled={busy || isEditing} onClick={() => void run(async () => { await updateResumeBullet(bullet.id, { ...factConfirmationPatch() }); setResumes(await readTargetResumes(missionId)); })}>确认事实</TextButton> : null}<TextButton disabled={busy || isEditing || ((needsTruthCheck || isSyntheticProject) && !factConfirmed)} onClick={() => void run(async () => { await updateResumeBullet(bullet.id, { status: "ACCEPTED" }); setResumes(await readTargetResumes(missionId)); })}>{statusLabel === "已接受" ? "已接受" : "接受"}</TextButton>{isEditing ? <><TextButton disabled={busy} onClick={() => { const built = buildTargetResumeInlineEditPatch(editingDraft); if (!built.ok) { setError(built.error); return; } void run(async () => { await updateResumeBullet(bullet.id, built.payload); setEditingBulletId(null); setEditingDraft(""); setResumes(await readTargetResumes(missionId)); }); }}>保存</TextButton><TextButton disabled={busy} onClick={() => { setEditingBulletId(null); setEditingDraft(""); }}>取消</TextButton></> : <TextButton disabled={busy} onClick={() => { setEditingBulletId(bullet.id); setEditingDraft(targetResumeBulletDisplayText(bullet)); }}>编辑</TextButton>}<TextButton disabled={busy || isEditing} onClick={() => void run(async () => { await updateResumeBullet(bullet.id, { status: "REJECTED" }); setResumes(await readTargetResumes(missionId)); })}>{statusLabel === "未采用" ? "未采用" : "不采用"}</TextButton></div></article>;
            })}
            {experienceSelection.filter((selection) => selection.decision === "OMIT" && !rewriteIds.has(selection.experience_id)).map((selection) => <article className="resume-ai-item" key={`omit-${selection.id}`}><h4>{experienceLabel(selection.experience_id).title}</h4><div className="resume-rewrite">AI 建议：暂不放入</div><div className="resume-ai-reason">{stripEvidenceDump(selection.why) || "与当前岗位核心要求关联较弱，建议把篇幅留给更强的科研、项目和竞赛经历。"}</div><div className="mission-bullet-actions"><TextButton disabled={busy} onClick={() => void updateDecision(selection.id, "KEEP")}>改为保留</TextButton></div></article>)}
            {experienceSelection.filter((selection) => (selection.decision === "KEEP_AND_HIGHLIGHT" || selection.decision === "KEEP" || selection.decision === "DEEMPHASIZE") && !rewriteIds.has(selection.experience_id)).map((selection) => {
              const decisionLabel = selection.decision === "KEEP_AND_HIGHLIGHT" ? "重点展示" : selection.decision === "KEEP" ? "保留" : "弱化";
              return <article className="resume-ai-item" key={`pending-rewrite-${selection.id}`}><h4>{experienceLabel(selection.experience_id).title}</h4><div className="resume-rewrite">已标记「{decisionLabel}」，正在等待改写要点。</div><div className="resume-ai-reason">这条经历已决定写入岗位版本，但改写要点尚未生成。点击下方按钮为当前决策重新生成改写。</div><div className="mission-bullet-actions"><TextButton disabled={busy} onClick={() => void run(async () => { await withTaskTimeout(generateMissionStep(missionId, "target-resumes"), 180_000, "岗位版本生成"); await refresh(); })}>生成这条的改写要点</TextButton></div></article>;
            })}
          </div>
        </div>
        <div className="mission-action-row mission-action-wrap" style={{ marginTop: "1rem" }}>
          {latestResume && !targetConfirmed ? <PrimaryButton disabled={busy || !bulletsDecided} onClick={() => void advanceResume()}>{busy ? "正在确认版本…" : "确认最终版本"}</PrimaryButton> : null}
          {latestResume && targetConfirmed ? <>
            <PrimaryButton disabled={busy} onClick={() => router.push(`/missions/${encodeURIComponent(missionId)}/resume/studio`)}>进入简历工作台并生成 PDF</PrimaryButton>
            <PrimaryButton disabled={busy} onClick={() => router.push(missionHref(missionId, "interview"))}>开始模拟面试</PrimaryButton>
          </> : null}
        </div>
        {latestResume && targetConfirmed ? <section className="resume-final-preview" aria-label="岗位定向文案预览">
          <div className="section-heading"><div><p className="section-kicker">确认版本</p><h3>岗位定向文案</h3><p className="summary">未完成且未确认的建议项目不进入 PDF。完整投递版及联系方式请在简历工作台核对。</p></div><TextButton disabled={busy} onClick={() => router.push(`/missions/${encodeURIComponent(missionId)}/resume/studio`)}>选择模板并导出 PDF</TextButton></div>
          <div className="mission-action-row" role="group" aria-label="简历版本">
            {(["original", "target"] as const).map((mode) => <button type="button" className={finalPreviewMode === mode ? "decision-chip active" : "decision-chip"} aria-pressed={finalPreviewMode === mode} key={mode} onClick={() => {
              const previousScroll = finalPreviewRef.current?.scrollTop ?? 0;
              setFinalPreviewMode(mode);
              requestAnimationFrame(() => { if (finalPreviewRef.current) finalPreviewRef.current.scrollTop = previousScroll; });
            }}>{mode === "original" ? "原始版本" : "岗位版本"}</button>)}
          </div>
          <div className="resume-final-preview-list" ref={finalPreviewRef}>{finalPreviewMode === "original" ? renderSourceResumeColumn() : (() => {
            const chosen = latestResume.bullets.filter((bullet) => isChosenRewrite(bullet.status));
            const highlightedIds = experienceSelection.filter((selection) => selection.decision === "KEEP_AND_HIGHLIGHT").map((selection) => selection.experience_id);
            const coveredIds = new Set(chosen.map((bullet) => bullet.source_experience_id).filter(Boolean));
            const missingHighlighted = highlightedIds.filter((id) => !coveredIds.has(id));
            const skills = latestResume.skills ?? [];
            return <>
              {chosen.map((bullet) => <article key={bullet.id}><strong>{bullet.source_experience_id ? experienceLabel(bullet.source_experience_id).title : confirmedProjectTitle(bullet.project_title)}</strong><p>{targetResumeBulletDisplayText(bullet)}</p></article>)}
              {missingHighlighted.map((id) => <article key={`missing-${id}`}><strong>{experienceLabel(id).title}</strong><p className="muted">这条经历已标记「重点展示」，但当前版本尚未包含它的改写要点——请在上方改写列表中采纳一条，或重新生成岗位版本。</p></article>)}
              {skills.length ? <article key="skills"><strong>个人技能</strong><p>{skills.join(" · ")}</p></article> : null}
            </>;
          })()}</div>
          <div className="resume-export-checks"><strong>来源档案检查（Studio 投递版为准）</strong><p className="summary">这里仅检查岗位内容；姓名、电话和邮箱以简历工作台中的投递版为准。</p>{buildPreExportChecklist({ profile: sourceProfile, experiences, bullets: latestResume.bullets, selections: experienceSelection, includeContactWarnings: false }).length ? <ul>{buildPreExportChecklist({ profile: sourceProfile, experiences, bullets: latestResume.bullets, selections: experienceSelection, includeContactWarnings: false }).map((item, index) => <li key={`${item.code}-${index}`}>{item.level === "block" ? "需处理" : "请留意"}：{item.message}</li>)}</ul> : <p>已完成内容检查。</p>}</div>
          {exportNotice ? <p className="summary" role="status">{exportNotice}</p> : null}
        </section> : null}
      </section>
    );
  }

  function renderResume() {
    const showOptimization = resumeStep !== "source" && !boundNeedsConfirm;
    const resumeHeading = resumeStep === "source"
      ? "简历来源"
      : resumeStep === "selection"
        ? "确认经历"
        : resumeStep === "strategy"
          ? "优化方向"
          : resumeStep === "target"
            ? "岗位定向版本"
            : "最终简历";
    return (
      <>
        <div className="mission-heading mission-heading-compact">
          <div>
            <p className="eyebrow">简历</p>
            <h2>{resumeHeading}</h2>
            <p className="summary">对照原始简历审阅岗位版本，确认后再进入模拟面试。</p>
          </div>
        </div>

        {confirmableProfileIdOf(currentMission) ? (
          <MissionProfileConfirmCard
            boundProfileId={confirmableProfileIdOf(currentMission)!}
            busy={busy}
            onConfirmed={async () => {
              setBoundNeedsConfirm(false);
              setOptimizationError("");
              await refresh();
              await run(async () => {
                await generateMissionStep(missionId, "claim-analysis");
                await refresh({ quiet: true });
              });
            }}
            onNeedsConfirmChange={setBoundNeedsConfirm}
          />
        ) : null}

        {resumeStep !== "source" && Boolean(currentMission.resume_source) && (
          <section className="mission-card">
            <div className="section-heading">
              <div>
                <p className="section-kicker">简历来源</p>
                <h3>当前：{resumeSourceLine(currentMission, experiences)}</h3>
                <p className="summary">若要改用上传 PDF 或粘贴文本，可在此更换；更换后会重新筛选经历。</p>
              </div>
              <TextButton
                disabled={busy}
                onClick={() => {
                  setForceResumeSource(true);
                  setModeTouched(false);
                  setUpdateMasterResume(false);
                  setMasterImpactLabel("");
                  setResumeMode(null);
                  setError("");
                }}
              >
                换简历来源
              </TextButton>
            </div>
          </section>
        )}

        {resumeStep === "source" && renderResumeSource()}

        {showOptimization && renderOptimizationWorkspace()}

        {resumeStep === "selection" && boundNeedsConfirm && (
          <section className="mission-card" role="status">
            <p className="section-kicker">待确认档案</p>
            <h3>上传/粘贴的岗位档案需先确认后再筛选经历</h3>
            <p className="summary">请先核对并确认简历内容，再继续选择经历。</p>
          </section>
        )}

        {!showOptimization && resumeStep === "selection" && !boundNeedsConfirm && (
          <section className="mission-card">
            <div className="section-heading">
              <div>
                <p className="section-kicker">选择经历</p>
                <h3>这份简历要保留哪些真实经历？</h3>
              </div>
              <span className="mission-disclaimer">点选即保存 · 「暂不放入」= 本份岗位简历不展示（不删原简历）</span>
            </div>
            {!experienceSelection.length ? (
              <p className="mission-empty">还没有筛选结果。点击下方主按钮，系统会先给出建议。</p>
            ) : (
              <ul className="mission-bullet-list">
                {dedupeExperienceSelections(experienceSelection, experienceMap).map((selection) => {
                  const label = experienceLabel(selection.experience_id);
                  return (
                    <li key={selection.id}>
                      <div>
                        <p className="experience-title">{label.title}</p>
                        <p className="experience-meta">{label.meta}</p>
                        <span>{alignedExperienceWhy(selection.decision, stripEvidenceDump(selection.why), experienceLabel(selection.experience_id).title)}</span>
                        <small>对应能力：{selection.related_capabilities.join("、") || "岗位通用"}</small>
                      </div>
                      <div className="decision-chip-row">
                        {EXPERIENCE_DECISION_OPTIONS.map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            className={selection.decision === option.value ? "decision-chip active" : "decision-chip"}
                            disabled={savingDecision || busy}
                            title={option.hint}
                            onClick={() => void updateDecision(selection.id, option.value)}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <PrimaryButton disabled={busy} onClick={() => void advanceResume()}>
              {busy ? "模型生成中…" : primaryCta(workflowState, ctaContext)}
            </PrimaryButton>
          </section>
        )}

        {!showOptimization && resumeStep === "strategy" && (
          <section className="mission-card">
            <p className="section-kicker">简历策略</p>
            <h3>针对这个岗位，这份简历应该讲怎样的候选人故事？</h3>
            {currentMission.resume_strategy && Object.keys(currentMission.resume_strategy).length ? (
              <>
                <p className="mission-bullet-text">{stripEvidenceDump(textOf(currentMission.resume_strategy.positioning_statement))}</p>
                <ul>
                  {Array.from(new Map(listOf(currentMission.resume_strategy.experience_guidance).map((item) => [
                    String(item.experience_id || item.role_in_story || "").trim(), item,
                  ])).values()).filter((item) => {
                    const role = textOf(item.role_in_story).trim();
                    return role && !/^support the target role narrative with confirmed evidence only\.?$/i.test(role);
                  }).map((item, index) => (
                    <li key={index}>
                      <strong>{textOf(item.role_in_story)}</strong>
                      <span>突出：{listOf(item.what_to_highlight).map(String).join("、")}</span>
                      <small>避免：{listOf(item.what_to_avoid).map(String).join("、") || "无"}</small>
                    </li>
                  ))}
                </ul>
                <p className="mission-pipeline-note">建议基于岗位要求生成；请逐条核对事实。</p>
              </>
            ) : (
              <p className="mission-empty">还没有策略。点击下方按钮，让模型根据你的经历和岗位 JD 生成候选人故事。</p>
            )}
            <PrimaryButton disabled={busy} onClick={() => void advanceResume()}>
              {busy ? "模型生成中…" : primaryCta(workflowState, ctaContext)}
            </PrimaryButton>
          </section>
        )}

        {!showOptimization && resumeStep === "target" && !latestResume && (
          <section className="mission-card">
            <div className="section-heading">
              <div>
                <p className="section-kicker">目标简历</p>
                <h3>还没有可用的目标简历草稿</h3>
                <p className="summary">
                  {error
                    ? error
                    : "生成未成功或引用了当前简历来源中不存在的经历。请重试生成，或返回经历筛选核对后再试。"}
                </p>
              </div>
            </div>
            <div className="mission-action-row mission-action-wrap">
              <PrimaryButton
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    setForceResumeStep(null);
                    await generateMissionStep(missionId, "target-resumes");
                  })
                }
              >
                {busy ? "模型生成中…" : "重试生成"}
              </PrimaryButton>
              <TextButton
                disabled={busy}
                onClick={() => {
                  setError("");
                  setForceResumeStep("selection");
                }}
              >
                返回经历筛选
              </TextButton>
            </div>
          </section>
        )}

        {!showOptimization && resumeStep === "target" && latestResume && (
          <section className="mission-card">
            <div className="section-heading">
              <div>
                <p className="section-kicker">
                  {isUnknownIdentity(currentMission.company) ? missionIdentityLabel(currentMission) : currentMission.company} 目标简历 v{latestResume.version}
                </p>
                <h3>核对要点后即可确认（默认已接受，可继续编辑 / 拒绝）</h3>
                <p className="mission-pipeline-note">投递版不单独生成「摘要」；教育与经历优先保留你上传简历中的原文（仅轻改）。</p>
              </div>
            </div>
            <ul className="mission-bullet-list">
                  {latestResume.bullets
                    .filter((bullet, index) => index < CORE_RESUME_SUGGESTION_LIMIT || (bullet.risk_flags ?? []).some((flag) => String(flag).toUpperCase() === "SYNTHETIC_PROJECT"))
                    .slice(0, CORE_RESUME_SUGGESTION_LIMIT + 2)
                    .map((bullet) => {
                    const isEditing = editingBulletId === bullet.id;
                    const statusLabel = targetResumeBulletStatusLabel(bullet.status);
                    const needsTruthCheck = bullet.grounding_status === "NEEDS_CONFIRMATION" || bullet.grounding_status === "UNSUPPORTED";
                    const isSyntheticProject = (bullet.risk_flags ?? []).some((flag) => String(flag).toUpperCase() === "SYNTHETIC_PROJECT");
                    return (
                <li key={bullet.id} className="mission-bullet-card">
                  <div className="mission-bullet-card-head">
                    <div>
                      <p className="section-kicker">原文</p>
                      <small>{bullet.original_text || "—"}</small>
                      {isEditing ? (
                        <textarea
                          className="textarea mission-bullet-edit-textarea"
                          rows={4}
                          value={editingDraft}
                          disabled={busy}
                          onChange={(event) => setEditingDraft(event.target.value)}
                          aria-label="编辑目标简历要点"
                        />
                      ) : (
                      <p className="mission-bullet-text">{targetResumeBulletDisplayText(bullet)}</p>
                      )}
                      {isSyntheticProject ? <small className="message warning" role="note">AI 项目草案：可直接编辑后放入目标简历。</small> : null}
                      <p className="section-kicker" style={{ marginTop: "0.55rem" }}>AI 建议</p>
                      <small>改写说明：{bullet.reason || "让岗位要求更容易在经历中被看见。"}</small>
                      <small>对应岗位关注：{(bullet.target_capabilities ?? []).slice(0, 3).join("、") || "与目标岗位要求相关"}</small>
                      {needsTruthCheck ? <small className="message warning" role="note">AI 建议补充，请确认是否真实做过；未确认前不会写入投递版。</small> : null}
                    </div>
                    {statusLabel === "已编辑" ? (
                      <span className="mission-bullet-badge mission-bullet-badge-edited">已编辑</span>
                    ) : null}
                    {statusLabel === "已接受" ? (
                      <span className="mission-bullet-badge mission-bullet-badge-accepted">已接受</span>
                    ) : null}
                    {statusLabel === "未采用" ? (
                      <span className="mission-bullet-badge mission-bullet-badge-rejected">已拒绝</span>
                    ) : null}
                  </div>
                  <div className="mission-bullet-actions">
                    <TextButton
                      disabled={busy || isEditing}
                      onClick={() =>
                        void run(async () => {
                          await updateResumeBullet(bullet.id, { status: "ACCEPTED" });
                          setResumes(await readTargetResumes(missionId));
                        })
                      }
                    >
                      接受
                    </TextButton>
                    {isEditing ? (
                      <>
                        <TextButton
                          disabled={busy}
                          onClick={() => {
                            const built = buildTargetResumeInlineEditPatch(editingDraft);
                            if (!built.ok) {
                              setError(built.error);
                              return;
                            }
                            void run(async () => {
                              await updateResumeBullet(bullet.id, built.payload);
                              setEditingBulletId(null);
                              setEditingDraft("");
                              setResumes(await readTargetResumes(missionId));
                            });
                          }}
                        >
                          保存
                        </TextButton>
                        <TextButton
                          disabled={busy}
                          onClick={() => {
                            setEditingBulletId(null);
                            setEditingDraft("");
                            setError("");
                          }}
                        >
                          取消
                        </TextButton>
                      </>
                    ) : (
                      <TextButton
                        disabled={busy}
                        onClick={() => {
                          setError("");
                          setEditingBulletId(bullet.id);
                          setEditingDraft(targetResumeBulletDisplayText(bullet));
                        }}
                      >
                        编辑
                      </TextButton>
                    )}
                    <TextButton
                      disabled={busy || isEditing}
                      onClick={() =>
                        void run(async () => {
                          await updateResumeBullet(bullet.id, { status: "REJECTED" });
                          setResumes(await readTargetResumes(missionId));
                        })
                      }
                    >
                      拒绝
                    </TextButton>
                  </div>
                </li>
                );
              })}
            </ul>
            {latestResume.bullets.length > CORE_RESUME_SUGGESTION_LIMIT ? (
              <p className="summary">已优先展示最值得修改的 {CORE_RESUME_SUGGESTION_LIMIT} 条建议。</p>
            ) : null}
            {targetConfirmed ? (
              <PrimaryButton disabled={busy} onClick={() => router.push(missionHref(missionId, "interview"))}>
                {coreResumeNextStep({ targetConfirmed: true }).label}
              </PrimaryButton>
            ) : (
              <PrimaryButton disabled={busy || !latestResume} onClick={() => void advanceResume()}>
                {busy ? "处理中…" : "确认优化建议"}
              </PrimaryButton>
            )}
            {latestResume && (
              <>
                <p className="summary" style={{ marginTop: 8 }}>
                  {exportEntryHint(countExportableBullets(latestResume, experiences.map((exp) => String(exp.id)).filter(Boolean)))}
                </p>
                <TextButton disabled={!latestResume || !targetConfirmed} onClick={() => router.push(`/missions/${encodeURIComponent(missionId)}/resume/studio`)}>
                  进入简历工作台，选择模板并下载 PDF
                </TextButton>
              </>
            )}
          </section>
        )}

        {(resumeStep === "stress" || resumeStep === "strengthen" || resumeStep === "ready") && latestResume && (
          <section className="mission-card" role="status">
            <p className="section-kicker">最终简历</p>
            <h3>简历已确认，可以投递或开始模拟面试</h3>
            <p className="summary">导出会沿用原简历的教育、经历、项目和技能结构，只替换你确认过的要点。</p>
            <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
              <PrimaryButton disabled={busy} onClick={() => router.push(`/missions/${encodeURIComponent(missionId)}/resume/studio`)}>
                打开简历工作台
              </PrimaryButton>
              <PrimaryButton disabled={busy} onClick={() => router.push(missionHref(missionId, "interview"))}>
                进入模拟面试
              </PrimaryButton>
              <TextButton disabled={busy} onClick={() => setForceResumeStep("target")}>
                查看优化建议
              </TextButton>
            </div>
            {exportNotice ? <p className="summary" role="status" style={{ marginTop: 8 }}>{exportNotice}</p> : null}
          </section>
        )}

        {debug && (
          <section className="mission-card">
            <p className="section-kicker">Debug panel</p>
            <div className="mission-action-row mission-action-wrap">
              <TextButton disabled={busy} onClick={() => void run(() => generateMissionStep(missionId, "experience-selection/generate"))}>
                generate selection
              </TextButton>
              <TextButton disabled={busy} onClick={() => void run(() => generateMissionStep(missionId, "resume-strategy"))}>
                generate strategy
              </TextButton>
              <TextButton disabled={busy} onClick={() => void run(() => generateMissionStep(missionId, "target-resumes"))}>
                generate resume
              </TextButton>
              <TextButton disabled={busy} onClick={() => void run(() => generateMissionStep(missionId, "red-team"))}>
                red team
              </TextButton>
              <TextButton disabled={busy} onClick={() => void run(() => generateMissionStep(missionId, "interview-pack"))}>
                interview pack
              </TextButton>
            </div>
          </section>
        )}
      </>
    );
  }

  function renderProof() {
    const claims = proof?.claims ?? [];
    const claimMockHref = mockInterviewHref(currentMission, { fresh: true });
    const needsStressTest = !redTeamLoading && !redTeamExecuted;
    return (
      <>
        <div className="mission-heading mission-heading-compact">
          <div>
            <p className="eyebrow">补强</p>
            <h2>把最容易被追问的部分补成真实证据</h2>
            <p className="summary">优先找回你已经做过的事实；确实没有时，再补完整现有项目。</p>
          </div>
        </div>
        {lastMockDebrief && lastMockDebrief.weakPoints.length ? (
          <section className="mission-card" style={{ marginBottom: "1rem" }}>
            <p className="section-kicker">来自最近一次模拟面试</p>
            <ul className="mission-bullet-list">
              {lastMockDebrief.weakPoints.slice(0, 6).map((point, index) => (
                <li key={`mock-weak-${index}`}><div><strong>待补强</strong><span>{point}</span></div></li>
              ))}
            </ul>
            {mockDebriefHref(currentMission) ? (
              <div className="mission-action-row" style={{ marginTop: "0.75rem" }}>
                <Link className="mission-secondary-cta link-cta" href={mockDebriefHref(currentMission)!}>
                  查看面试结果
                </Link>
              </div>
            ) : null}
          </section>
        ) : null}
        {confirmableProfileIdOf(currentMission) ? (
          <div id="mission-profile-confirm-anchor">
            <MissionProfileConfirmCard
              boundProfileId={confirmableProfileIdOf(currentMission)!}
              busy={busy}
              onConfirmed={async () => {
                setBoundNeedsConfirm(false);
                setOptimizationError("");
                await refresh();
                await run(async () => {
                  await generateMissionStep(missionId, "claim-analysis");
                  await refresh({ quiet: true });
                });
              }}
              onNeedsConfirmChange={setBoundNeedsConfirm}
            />
          </div>
        ) : null}
        {redTeamLoading && (
          <section className="mission-empty" role="status">
            <p>正在同步压力测试结果…</p>
          </section>
        )}
        {needsStressTest && !(proof?.proof_actions?.length) && (
          <section className="mission-card" role="status">
            <p className="section-kicker">可选</p>
            <p className="summary">压力测试能帮你发现高风险追问；补强步骤不必等它完成——可直接为薄弱主张生成可执行动作。</p>
            <div className="mission-action-row" style={{ marginTop: "0.75rem" }}>
              <TextButton
                disabled={busy}
                onClick={() => router.push(missionHref(missionId, "resume"))}
              >
                去压力测试
              </TextButton>
            </div>
          </section>
        )}
        {boundNeedsConfirm ? (
          <section className="mission-card" role="status" id="mission-profile-confirm-gate">
            <p className="section-kicker">需先确认档案</p>
            <h3>证明补强需要先确认个人档案</h3>
            <p className="summary">请先在本页上方确认这份简历中的事实。确认前「找出最危险的一项」不可用。</p>
            <div className="mission-action-row" style={{ marginTop: "0.75rem" }}>
              <button
                type="button"
                className="button-secondary"
                onClick={() => {
                  document.getElementById("mission-profile-confirm-anchor")?.scrollIntoView({
                    behavior: "smooth",
                    block: "center",
                  });
                }}
              >
                确认简历内容
              </button>
            </div>
          </section>
        ) : null}
        <div className="mission-action-row">
          <PrimaryButton
            disabled={busy || boundNeedsConfirm}
            onClick={() => void run(() => generateMissionStep(missionId, "claim-analysis"))}
          >
            {claims.length ? "刷新薄弱点" : "找出最危险的一项"}
          </PrimaryButton>
        </div>
        {claims.length ? (
          <ul className="mission-bullet-list">
            {claims.map((claim) => {
              const claimActions = (proof?.proof_actions ?? []).filter((action) => action.claim_id === claim.id);
              return (
              <li key={claim.id} id={`mission-claim-${claim.id}`}>
                <div>
                  <strong>{claim.claim}</strong>
                  <span>
                    {readinessStatusLabel(claim.readiness_status)} · {Math.round(claim.confidence * 100)}%
                    {" · "}
                    {claimStrengthenProgressLabel({
                      readinessStatus: claim.readiness_status,
                      actionStatuses: claimActions.map((action) => action.status),
                      hasArtifact: (proof?.proof_artifacts ?? []).some((artifact) => artifact.claim_id === claim.id),
                      markedNoExperience: hasCompletedNoExperienceAction(claimActions),
                    })}
                  </span>
                  <small>{claim.risk_reason}</small>
                </div>
                <div className="mission-bullet-actions">
                  <TextButton
                    disabled={busy}
                    onClick={() => {
                      setRecoverDraftClaimId(claim.id);
                      setRecoverDraftText("");
                      setActiveActionId(null);
                      setError("");
                      setProofNotice("");
                    }}
                  >
                    找回已有证据
                  </TextButton>
                  <TextButton
                    disabled={busy}
                    onClick={() => {
                      void run(async () => {
                        const actions = await generateProofActionsForMission(missionId, claim.id);
                        if (!actions.length) {
                          throw new Error("还没有生成可执行补强动作。请确认档案后重试，或改用「找回已有证据」。");
                        }
                      });
                    }}
                  >
                    补完整现有项目
                  </TextButton>
                </div>
                {recoverDraftClaimId === claim.id ? (
                  <div className="mission-card" style={{ marginTop: "0.75rem" }}>
                    <p className="section-kicker">找回已有证据</p>
                    <p className="summary">写下可核对的事实、材料线索或项目结果。取消则不会提交。</p>
                    <textarea
                      value={recoverDraftText}
                      onChange={(event) => setRecoverDraftText(event.target.value)}
                      rows={4}
                      placeholder="例如：2023 年我在 XX 项目负责评测门禁，有周报/截图可核对…"
                      style={{ width: "100%" }}
                    />
                    <div className="mission-action-row" style={{ marginTop: "0.5rem" }}>
                      <PrimaryButton
                        disabled={busy || !recoverDraftText.trim()}
                        onClick={() => {
                          const note = recoverDraftText.trim();
                          if (!note) {
                            setError("请先填写可核对的证据说明。");
                            return;
                          }
                          void run(async () => {
                            const result = await recoverEvidence(missionId, {
                              claim_id: claim.id,
                              confirmed: true,
                              evidence_text: note,
                              artifact_text: note,
                            });
                            const message = typeof result.message === "string" ? result.message.trim() : "";
                            setProofNotice(message || "已记录这条证据，可继续补充材料。 ");
                            setRecoverDraftClaimId(null);
                            setRecoverDraftText("");
                          });
                        }}
                      >
                        提交已有证据
                      </PrimaryButton>
                      <TextButton
                        disabled={busy}
                        onClick={() => {
                          setRecoverDraftClaimId(null);
                          setRecoverDraftText("");
                        }}
                      >
                        取消
                      </TextButton>
                    </div>
                  </div>
                ) : null}
                {claimActions.length ? (
                  <ul className="mission-bullet-list" style={{ marginTop: "0.75rem" }}>
                    {claimActions.map((action) => (
                      <li key={action.id}>
                        <div>
                          <strong>{action.title}</strong>
                          <span>{proofActionStatusLabel(action.status)}</span>
                          <small>{action.definition_of_done}</small>
                        </div>
                        <div className="mission-bullet-actions">
                          <TextButton
                            disabled={busy || action.status === "COMPLETED" || action.status === "SKIPPED"}
                            onClick={() => {
                              setActiveActionId(action.id);
                              setActionDraftText("");
                              setRecoverDraftClaimId(null);
                              setError("");
                            }}
                          >
                            {action.artifact_type === "NO_EXPERIENCE_MARK" || action.title.includes("我没有这段经历")
                              ? "确认没有这段经历"
                              : action.artifact_type === "NON_CLAIMABLE_MARK" || action.title.includes("暂不可主张")
                                ? "确认暂不主张"
                                : "填写 / 上传"}
                          </TextButton>
                        </div>
                        {activeActionId === action.id ? (
                          <div className="mission-card" style={{ marginTop: "0.5rem" }}>
                            <p className="summary">{action.expected_evidence}</p>
                            <textarea
                              value={actionDraftText}
                              onChange={(event) => setActionDraftText(event.target.value)}
                              rows={4}
                              placeholder="填写事实、项目说明、材料链接，或确认标记…"
                              style={{ width: "100%" }}
                            />
                            <div className="mission-action-row" style={{ marginTop: "0.5rem" }}>
                              <PrimaryButton
                                disabled={busy || !actionDraftText.trim()}
                                onClick={() => {
                                  const note = actionDraftText.trim();
                                  if (!note) {
                                    setError("请先填写内容再提交。");
                                    return;
                                  }
                                  void run(async () => {
                                    await submitMissionProofArtifact(action.id, {
                                      action_id: action.id,
                                      artifact_type: action.artifact_type || "USER_NOTE",
                                      artifact_text: note,
                                      manually_confirmed: true,
                                    });
                                    setActiveActionId(null);
                                    setActionDraftText("");
                                  });
                                }}
                              >
                                提交这一步
                              </PrimaryButton>
                              <TextButton
                                disabled={busy}
                                onClick={() => {
                                  setActiveActionId(null);
                                  setActionDraftText("");
                                }}
                              >
                                取消
                              </TextButton>
                            </div>
                          </div>
                        ) : null}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="summary" style={{ marginTop: "0.5rem" }}>
                    还没有可执行步骤。点「补完整现有项目」生成，或先「找回已有证据」。
                  </p>
                )}
              </li>
              );
            })}
          </ul>
        ) : (
          <section className="mission-empty">还没有薄弱点列表。先找出最危险的一项，或从压力测试里的高风险项开始。</section>
        )}
        {proofNotice ? <p className="message success" role="status" style={{ marginTop: "0.75rem" }}>{proofNotice}</p> : null}
        {claims.length > 0 && !(proof?.proof_actions?.length) && !boundNeedsConfirm ? (
          <section className="mission-card" role="status" style={{ marginTop: "1rem", borderColor: "var(--warning, #c47b1a)" }}>
            <p className="section-kicker">下一步</p>
            <h3>先为薄弱主张生成可执行步骤</h3>
            <p className="summary">
              {strengthenStatusSummary(readiness?.status) || "当前主张证据偏弱。"}
              点某一条上的「补完整现有项目」生成具体步骤（事实追问、补项目、上传材料，或标记没有这段经历）。
              若岗位绑错了简历，再换绑真实简历。
            </p>
            <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
              <PrimaryButton
                disabled={busy}
                onClick={() => {
                  const first = claims[0];
                  if (!first) return;
                  void run(async () => {
                    await generateProofActionsForMission(missionId, first.id);
                  });
                }}
              >
                为第一条生成补强步骤
              </PrimaryButton>
              <TextButton
                disabled={busy}
                onClick={() => {
                  setForceResumeSource(true);
                  setModeTouched(false);
                  setUpdateMasterResume(false);
                  setResumeMode(null);
                  setUploadFile(null);
                  setPasteText("");
                  setError("");
                  router.push(missionHref(missionId, "resume"));
                }}
              >
                重新上传 / 换绑简历
              </TextButton>
              <TextButton
                disabled={busy}
                onClick={() => void run(() => generateMissionStep(missionId, "claim-analysis"))}
              >
                刷新补强分析
              </TextButton>
            </div>
          </section>
        ) : null}
        <section
          className="mission-card"
          role="navigation"
          aria-label="补强下一步"
          style={{ marginTop: "1rem", position: "sticky", bottom: 0, zIndex: 2, background: "var(--card-bg, #fff)", borderColor: "var(--border, #ddd)" }}
        >
          <p className="section-kicker">下一步</p>
          {proofNextStep.kind === "resume" ? (
            <>
              <h3>先确认目标简历</h3>
              <p className="summary">补强动作依赖已确认的目标简历。先回到简历步骤完成确认，再继续补强。</p>
              <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
                <PrimaryButton disabled={busy} onClick={() => router.push(missionHref(missionId, "resume"))}>
                  {proofNextStep.label}
                </PrimaryButton>
                <TextButton disabled={busy} onClick={() => void refresh()}>重试评估</TextButton>
              </div>
            </>
          ) : readiness == null ? (
            <>
              <h3>准备度暂未同步</h3>
              <p className="summary">刷新后会更新薄弱主张与面试入口。</p>
              <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
                <PrimaryButton disabled={busy} onClick={() => void refresh()}>重试评估</PrimaryButton>
              </div>
            </>
          ) : proofNextStep.kind === "strengthen" ? (
            <>
              <h3>还有 {Math.max(evidenceGapCount, claims.filter((c) => /WEAK|UNSUPPORTED/i.test(String(c.readiness_status || ""))).length, 1)} 项证据待补强</h3>
              <p className="summary">{strengthenStatusSummary(readiness.status) || "先把可追问材料补齐，再进入模拟面试。"}</p>
              <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
                <PrimaryButton
                  disabled={busy || !claims.length}
                  onClick={() => {
                    const first = claims.find((c) => /WEAK|UNSUPPORTED/i.test(String(c.readiness_status || ""))) ?? claims[0];
                    if (!first) return;
                    document.getElementById(`mission-claim-${first.id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
                  }}
                >
                  {proofNextStep.label}
                </PrimaryButton>
                {interviewCta.canStartClaimMock && claimMockHref ? (
                  <Link className="mission-secondary-cta link-cta" href={claimMockHref}>
                    先练习单主张拷问
                  </Link>
                ) : null}
                <TextButton disabled={busy} onClick={() => void refresh()}>重试评估</TextButton>
              </div>
            </>
          ) : (
            <>
              <h3>{interviewableClaimsOk ? "可以进入面试准备" : "先确认可面试主张"}</h3>
              <p className="summary">
                {interviewableClaimsOk
                  ? "下一步去面试页生成准备包或开始模拟拷问；全岗就绪与单主张模拟由面试页区分。"
                  : "当前还没有可追问主张。补一条有履历证据的主张后再进入面试。"}
              </p>
              <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
                <PrimaryButton
                  disabled={busy || !interviewableClaimsOk}
                  onClick={() => {
                    markProofVisited(missionId);
                    router.push(missionHref(missionId, "interview"));
                  }}
                >
                  {proofNextStep.label}
                </PrimaryButton>
                <TextButton disabled={busy} onClick={() => void refresh()}>重试评估</TextButton>
              </div>
            </>
          )}
        </section>
      </>
    );
  }

  async function generateQuestions() {
    setBusy(true);
    setQuestionError("");
    setQuestionStage(0);
    try {
      await withTaskTimeout(generateMissionStep(missionId, "interview-pack"), 180_000, "问题生成");
      setQuestionStage(1);
      setInterviewPack(await withTaskTimeout(readInterviewPack(missionId), 30_000, "问题读取"));
      setQuestionStage(null);
    } catch (caught) {
      setQuestionError(humanizeMissionError(caught instanceof Error ? caught.message : "", "generic"));
    } finally {
      setBusy(false);
    }
  }

  function renderInterview() {
    const hasPack = interviewPack.topics.length > 0;
    const copy = coreInterviewCopy({ hasFinalResume: targetConfirmed, hasQuestions: hasPack });
    const mockHref = mockInterviewHref(currentMission, { fresh: true });
    return (
      <>
        <div className="mission-heading mission-heading-compact">
          <div>
            <p className="eyebrow">模拟面试</p>
            <h2>{copy.title}</h2>
            <p className="summary">{copy.description}</p>
          </div>
        </div>
        {lastMockDebrief ? (
          <section className="mission-card" style={{ marginBottom: "1rem" }}>
            <p className="section-kicker">最近一次练习</p>
            <p className="summary">
              {lastMockDebrief.weakPoints.length
                ? `建议继续练习：${lastMockDebrief.weakPoints.slice(0, 3).join("；")}`
                : "上一轮练习已完成，可以重新开始一轮。"}
            </p>
            {mockDebriefHref(currentMission) ? (
              <Link className="mission-secondary-cta link-cta" href={mockDebriefHref(currentMission)!}>
                查看本轮记录
              </Link>
            ) : null}
          </section>
        ) : null}
        {!targetConfirmed ? (
          <section className="mission-card" role="status">
            <p className="section-kicker">先完成简历</p>
            <h3>确认最终简历后再开始模拟面试</h3>
            <p className="summary">面试问题会直接围绕你确认过的经历生成。</p>
            <PrimaryButton disabled={busy} onClick={() => router.push(missionHref(missionId, "resume"))}>
              回到简历优化
            </PrimaryButton>
          </section>
        ) : (
          <>
            <section className="mission-card" role="status">
              <p className="section-kicker">面试准备</p>
              <h3>{hasPack ? "问题预览已生成" : "先生成问题预览"}</h3>
              <p className="summary">先查看考察主题，再按题作答。</p>
              <div className="mission-action-row mission-action-wrap" style={{ marginTop: "0.75rem" }}>
                {!hasPack ? (
                  <PrimaryButton disabled={busy} onClick={() => void generateQuestions()}>
                    {busy ? "正在生成问题…" : "生成问题预览"}
                  </PrimaryButton>
                ) : null}
                <TextButton
                  disabled={busy}
                  onClick={() => void generateQuestions()}
                >
                  {busy ? "正在生成问题…" : hasPack ? "重新生成问题预览" : "重新生成"}
                </TextButton>
              </div>
              {questionStage !== null && <TaskProgress kind="interview-questions" activeIndex={questionStage} error={questionError} onRetry={() => void generateQuestions()} />}
            </section>
            {hasPack ? (
              <section className="mission-card">
                <p className="section-kicker">问题预览</p>
                <div className="interview-preview-list">
                  {interviewPack.topics.slice(0, 8).map((topic, index) => {
                    const questions = stringsOf(topic.question_patterns ?? topic.questions ?? topic.question);
                    return (
                      <details className="interview-preview-card" key={index} open={index === 0}>
                        <summary><span className="preview-index">{String(index + 1).padStart(2, "0")}</span><span><strong>{textOf(topic.topic) || `问题 ${index + 1}`}</strong><small>{questions[0] || "请结合一段真实经历回答。"}</small></span></summary>
                        <div className="interview-preview-focus"><strong>考察点</strong><p>{textOf(topic.why) || "与目标岗位和简历经历相关"}</p>{questions.slice(1).map((question, questionIndex) => <p key={questionIndex}>{question}</p>)}</div>
                      </details>
                    );
                  })}
                </div>
                {mockHref && <div className="interview-preview-action"><Link className="mission-primary-cta link-cta" href={mockHref}>开始模拟面试</Link></div>}
              </section>
            ) : null}
          </>
        )}
      </>
    );
  }
  function renderOutcome() {
    return (
      <>
        <div className="mission-heading mission-heading-compact">
          <div>
            <p className="eyebrow">面试记录</p>
            <h2>记录一次真实面试</h2>
            <p className="summary">把公司、岗位、轮次、问题和复盘留在这里，下一次练习时继续使用。</p>
          </div>
        </div>
        <form
          className="mission-card mission-form"
          onSubmit={(event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const interview_round = String(form.get("interview_round") || "").trim();
            const questions_asked = String(form.get("questions_asked") || "")
              .split("\n")
              .map((item) => item.trim())
              .filter(Boolean);
            const where_struggled = String(form.get("where_struggled") || "").trim();
            const interviewer_feedback = String(form.get("interviewer_feedback") || "").trim();
            const debriefError = validateMissionDebrief({
              interview_round,
              questions_asked,
              where_struggled,
              interviewer_feedback,
            });
            if (debriefError) {
              setOutcomeMessage("");
              setError(debriefError);
              return;
            }
            void run(async () => {
              await submitMissionOutcome(missionId, {
                application_status: String(form.get("application_status") || "INTERVIEWING"),
                interview_round,
                questions_asked,
                where_struggled,
                interviewer_feedback,
                notes: String(form.get("notes") || ""),
                confirmed_for_intel: form.get("confirmed_for_intel") === "on",
              });
              setOutcomeMessage("复盘已保存。");
            });
          }}
        >
          <label className="field-label">
            面试结果
            <select name="application_status" defaultValue="INTERVIEWING">
              <option>APPLIED</option>
              <option>INTERVIEWING</option>
              <option>ACCEPTED</option>
              <option>REJECTED</option>
              <option>WITHDRAWN</option>
            </select>
          </label>
          <label className="field-label">
            面试轮次
            <input name="interview_round" />
          </label>
          <label className="field-label">
            被问到的问题
            <textarea name="questions_asked" rows={4} />
          </label>
          <label className="field-label">
            需要加强的地方
            <textarea name="where_struggled" rows={3} />
          </label>
          <label className="field-label">
            我的回答 / 复盘
            <textarea name="notes" rows={4} placeholder="记录自己的回答、当时的思路和下次准备方式" />
          </label>
          <label className="field-label">
            面试官反馈
            <textarea name="interviewer_feedback" rows={3} />
          </label>
          <button type="submit" className="mission-primary-cta" disabled={busy}>
            {busy ? "保存中…" : "保存复盘"}
          </button>
          {outcomeMessage && (
            <p className="message success" role="status">
              {outcomeMessage}
            </p>
          )}
        </form>
      </>
    );
  }

  function renderOverviewStatus() {
    return (
      <>
        <div className="mission-heading mission-heading-compact">
          <div>
            <p className="eyebrow">状态总览</p>
            <h2>
              {missionIdentityLabel(currentMission)}
            </h2>
            <p className="summary">当前进度：{workflowStateLabel(workflowState)}。点继续准备回到正确的下一步。</p>
          </div>
        </div>
        <section className="mission-card">
          <ul className="mission-intel-summary">
            <li>工作流状态：<strong>{workflowStateLabel(workflowState)}</strong></li>
            <li>简历来源：<strong>{resumeSourceLine(currentMission, experiences)}</strong></li>
            <li>高风险追问：<strong>{highRiskCount}</strong></li>
          </ul>
          <PrimaryButton disabled={busy} onClick={() => router.push(nextRoute(workflowState, missionId) as never)}>
            继续准备
          </PrimaryButton>
        </section>
      </>
    );
  }

  const shellTab = currentTab === "overview" ? "role" : currentTab;

  return (
    <MissionShell mission={currentMission} currentTab={shellTab} compactHints={compactHints} progressSteps={deriveMissionProgress({
      missionId,
      workflowState: currentMission.workflow_state,
      currentTab: shellTab === "proof" ? "resume" : shellTab,
      resumeBound,
      targetConfirmed,
      sessionStatus: interviewSessionStatus,
    })}>
      <div className="mission-content">
        {exportNotice && (
          <div className="mission-action-row mission-action-wrap" style={{ marginBottom: "0.75rem" }}>
            <p className="message warning" role="status">
              {exportNotice}
            </p>
            <TextButton onClick={() => setExportNotice("")}>知道了</TextButton>
          </div>
        )}
        {error && (
          <div className="mission-action-row mission-action-wrap" style={{ marginBottom: "0.75rem" }}>
            <p className="message error" role="alert">
              {error}
            </p>
            <TextButton
              onClick={() => {
                setError("");
                void refresh();
              }}
            >
              重试
            </TextButton>
            <Link className="button-secondary" href={missionHref(missionId, "resume")}>
              返回简历
            </Link>
            {(error.includes("压力测试") && (error.includes("补强") || error.includes("创建"))) && (
              <PrimaryButton disabled={busy} onClick={() => router.push(missionHref(missionId, "resume"))}>
                去压力测试
              </PrimaryButton>
            )}
          </div>
        )}
        {currentTab === "overview" && renderOverviewStatus()}
        {currentTab === "role" && renderRole()}
        {currentTab === "resume" && renderResume()}
        {currentTab === "proof" && renderProof()}
        {currentTab === "interview" && renderInterview()}
        {currentTab === "outcome" && renderOutcome()}
      </div>
    </MissionShell>
  );
}
