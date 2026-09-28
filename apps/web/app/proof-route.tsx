"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

import { ProofShell } from "./proof-shell.tsx";
import { canEnterProofStep, latestValidProofStep, proofHref, PROOF_API_BASE_URL, shouldKeepMissionInterviewRoute } from "./proof-state.ts";
import type { ProofSnapshot, ProofStep } from "./proof-state.ts";
import { readProofSnapshot } from "./proof-state.ts";

export type ProofNextAction = () => Promise<boolean>;
export type ProofStepControls = {
  profileId: string;
  apiUrl: string;
  busy: boolean;
  refresh: () => Promise<ProofSnapshot | null>;
  setNextReady: (ready: boolean) => void;
  setNextAction: (action: ProofNextAction | null) => void;
  setStepError: (message: string) => void;
  setSnapshot: (snapshot: ProofSnapshot) => void;
};

type ProofRouteProps = { profileId: string; missionId?: string; currentStep: ProofStep; renderStep: (snapshot: ProofSnapshot, controls: ProofStepControls) => ReactNode };

export function ProofRoute({ profileId, missionId, currentStep, renderStep }: ProofRouteProps) {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<ProofSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [nextReady, setNextReady] = useState(false);
  const [error, setError] = useState("");
  const requestSerial = useRef(0);
  const nextAction = useRef<ProofNextAction | null>(null);
  const claimBootstrapAttempted = useRef(false);

  const load = useCallback(async (showLoading: boolean) => {
    const serial = ++requestSerial.current;
    if (showLoading) setLoading(true);
    setError("");
    try {
      let result = await readProofSnapshot(profileId, PROOF_API_BASE_URL, fetch, missionId);
      if (serial !== requestSerial.current) return null;
      // Mission interview links are entered directly from the confirmed
      // resume. Older missions may not have a claim-analysis envelope yet;
      // generate it once here instead of redirecting through the removed
      // resume-suggestions/claim-check screens.
      if (currentStep === "interview" && missionId && result.targetJob && !result.claim && !claimBootstrapAttempted.current) {
        claimBootstrapAttempted.current = true;
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), 20_000);
        try {
          const response = await fetch(`${PROOF_API_BASE_URL}/api/v1/job-missions/${encodeURIComponent(missionId)}/claim-analysis`, { method: "POST", signal: controller.signal });
          if (response.ok) result = await readProofSnapshot(profileId, PROOF_API_BASE_URL, fetch, missionId);
          else setError("面试问题准备失败，请点击重试。");
        } catch (bootstrapError) {
          if (bootstrapError instanceof DOMException && bootstrapError.name === "AbortError") setError("面试问题准备超过 20 秒，请点击重试。");
          else throw bootstrapError;
        } finally {
          clearTimeout(timer);
        }
      }
      if (serial !== requestSerial.current) return null;
      setSnapshot(result);
      const allowed = canEnterProofStep(result, currentStep);
      if (!allowed) {
        if (shouldKeepMissionInterviewRoute(result, missionId, currentStep)) {
          setError("正在准备第 1 题，请稍候；如果超过 20 秒仍未出现，请点击重试。");
          return result;
        }
        const destination = proofHref(profileId, latestValidProofStep(result), missionId);
        setSnapshot(null);
        if (destination !== proofHref(profileId, currentStep, missionId)) router.replace(destination);
        else setError("当前证明步骤的前置条件尚未完成。");
        return null;
      }
      return result;
    } catch (loadError) {
      if (serial !== requestSerial.current) return null;
      setError(loadError instanceof Error ? loadError.message : "无法加载证明链状态，请重试。");
      return null;
    } finally {
      if (serial === requestSerial.current && showLoading) setLoading(false);
    }
  }, [currentStep, missionId, profileId, router]);

  useEffect(() => { void load(true); return () => { requestSerial.current += 1; }; }, [load]);
  const refresh = useCallback(() => load(false), [load]);
  const controls: ProofStepControls = {
    profileId,
    apiUrl: PROOF_API_BASE_URL,
    busy,
    refresh,
    setNextReady,
    setNextAction: (action) => { nextAction.current = action; },
    setStepError: setError,
    setSnapshot,
  };

  async function handleNext() {
    const index = ["target-job", "resume-suggestions", "claim-check", "interview", "debrief", "proof-actions", "re-evaluate"].indexOf(currentStep);
    const nextStep = ["target-job", "resume-suggestions", "claim-check", "interview", "debrief", "proof-actions", "re-evaluate"][index + 1] as ProofStep | undefined;
    if (!nextStep || busy) return;
    setBusy(true);
    setError("");
    try {
      // A completed interview can leave a stale submit closure in the ref
      // for one render. Navigate directly to the debrief instead of posting
      // the last answer again (which previously produced a silent 409).
      if (currentStep === "interview" && snapshot?.session?.status === "COMPLETED") {
        router.push(proofHref(profileId, "debrief", missionId));
        return;
      }
      const action = nextAction.current;
      const ranAction = Boolean(action);
      if (action && !(await action())) return;
      // Interview submission already replaces the local session with the
      // server response. Do not wait for a second full proof snapshot here:
      // that slow read used to leave the newly rendered next question behind
      // a disabled "正在评分…" footer and made the next click a no-op.
      if (currentStep === "interview" && ranAction) return;
      // Keep mission scope — same path the left rail already uses via loaded snapshot.
      const persisted = await readProofSnapshot(profileId, PROOF_API_BASE_URL, fetch, missionId);
      setSnapshot(persisted);
      if (currentStep === "interview" && persisted.session?.status === "ACTIVE") {
        setNextReady(false);
        return;
      }
      if (!canEnterProofStep(persisted, nextStep)) {
        setNextReady(false);
        if (nextStep === "claim-check" && !persisted.analysis?.claims.length) {
          setError("还没有可核对的简历主张。请先生成主张分析（继续时会自动生成），完成后再进入主张核对。");
        } else {
          setError("当前步骤尚未完成，请先保存后再继续。");
        }
        return;
      }
      router.push(proofHref(profileId, nextStep, missionId));
    } catch (nextError) {
      const raw = nextError instanceof Error ? nextError.message : "";
      if (/Claim analysis has not been generated|尚未生成主张分析/i.test(raw)) {
        setError("还没有可核对的简历主张。请先生成主张分析，或从左侧进入「主张核对」。");
      } else {
        setError(raw || "无法继续当前步骤，请重试。");
      }
    } finally {
      setBusy(false);
    }
  }

  return <ProofShell missionId={missionId} profileId={profileId} currentStep={currentStep} snapshot={snapshot} loading={loading} busy={busy} nextReady={nextReady} error={error} onNext={() => void handleNext()} onRetry={() => void load(true)}>{snapshot ? renderStep(snapshot, controls) : null}</ProofShell>;
}
