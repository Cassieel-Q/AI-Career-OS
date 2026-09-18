"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

import {
  API_BASE_URL,
  canEnterStep,
  latestValidStep,
  readWorkflowSnapshot,
  workflowHref,
  WorkflowProfileNotFoundError,
} from "./workflow-state.ts";
import type { WorkflowSnapshot, WorkflowStep } from "./workflow-state.ts";
import { canNavigateNext, stepNavigation } from "./workflow-navigation.ts";
import { WorkflowShell } from "./workflow-shell.tsx";

export type WorkflowNextAction = () => Promise<boolean>;

export type WorkflowStepControls = {
  apiUrl: string;
  busy: boolean;
  refresh: () => Promise<WorkflowSnapshot | null>;
  setNextReady: (ready: boolean) => void;
  setNextAction: (action: WorkflowNextAction | null) => void;
  setStepError: (message: string) => void;
};

type WorkflowRouteProps = {
  profileId: string;
  currentStep: WorkflowStep;
  renderStep: (snapshot: WorkflowSnapshot, controls: WorkflowStepControls) => ReactNode;
};

function latestHref(profileId: string, snapshot: WorkflowSnapshot): import("next").Route {
  const step = latestValidStep(snapshot);
  return step === "start" ? "/workflow/start" : workflowHref(profileId, step);
}

export function WorkflowRoute({ profileId, currentStep, renderStep }: WorkflowRouteProps) {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<WorkflowSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [nextReady, setNextReady] = useState(false);
  const [error, setError] = useState("");
  const activeRequest = useRef(0);
  const nextAction = useRef<WorkflowNextAction | null>(null);

  const loadWorkflow = useCallback(async (showLoading: boolean): Promise<WorkflowSnapshot | null> => {
    const requestId = ++activeRequest.current;
    let redirecting = false;
    if (showLoading) setLoading(true);
    setError("");
    try {
      const result = await readWorkflowSnapshot(profileId, API_BASE_URL);
      if (requestId !== activeRequest.current) return null;
      setSnapshot(result);
      setNextReady(canNavigateNext(result, currentStep));
      if (!canEnterStep(result, currentStep)) {
        const destination = latestHref(profileId, result);
        setSnapshot(null);
        setNextReady(false);
        setLoading(true);
        redirecting = true;
        if (destination !== workflowHref(profileId, currentStep)) router.replace(destination);
        return null;
      }
      return result;
    } catch (loadError) {
      if (requestId !== activeRequest.current) return null;
      if (loadError instanceof WorkflowProfileNotFoundError) {
        router.replace("/workflow/start");
        return null;
      }
      setError(loadError instanceof Error ? loadError.message : "无法加载当前流程状态，请重试。");
      return null;
    } finally {
      if (requestId === activeRequest.current && showLoading && !redirecting) setLoading(false);
    }
  }, [currentStep, profileId, router]);

  useEffect(() => {
    void loadWorkflow(true);
    return () => { activeRequest.current += 1; };
  }, [loadWorkflow]);

  const refresh = useCallback(() => loadWorkflow(false), [loadWorkflow]);
  const setNextAction = useCallback((action: WorkflowNextAction | null) => {
    nextAction.current = action;
  }, []);
  const setStepError = useCallback((message: string) => setError(message), []);

  async function handleNext() {
    const nextUrl = stepNavigation(profileId, currentStep).next;
    if (!nextUrl || busy) return;
    setBusy(true);
    setError("");
    try {
      let latest: WorkflowSnapshot;
      try {
        latest = await readWorkflowSnapshot(profileId, API_BASE_URL);
      } catch (loadError) {
        if (loadError instanceof WorkflowProfileNotFoundError) {
          router.replace("/workflow/start");
          return;
        }
        throw loadError;
      }
      if (!canEnterStep(latest, currentStep)) {
        const destination = latestHref(profileId, latest);
        setSnapshot(null);
        setNextReady(false);
        setLoading(true);
        if (destination !== workflowHref(profileId, currentStep)) router.replace(destination);
        return;
      }
      const action = nextAction.current;
      if (action) {
        const actionCompleted = await action();
        if (!actionCompleted) return;
        let persisted: WorkflowSnapshot;
        try {
          persisted = await readWorkflowSnapshot(profileId, API_BASE_URL);
        } catch (loadError) {
          if (loadError instanceof WorkflowProfileNotFoundError) {
            router.replace("/workflow/start");
            return;
          }
          throw loadError;
        }
        setSnapshot(persisted);
        if (!canNavigateNext(persisted, currentStep)) {
          const destination = latestHref(profileId, persisted);
          setSnapshot(null);
          setNextReady(false);
          setLoading(true);
          if (destination !== workflowHref(profileId, currentStep)) router.replace(destination);
          return;
        }
      } else if (!canNavigateNext(latest, currentStep)) {
        const destination = latestHref(profileId, latest);
        setSnapshot(null);
        setNextReady(false);
        setLoading(true);
        if (destination !== workflowHref(profileId, currentStep)) router.replace(destination);
        return;
      } else {
        setSnapshot(latest);
      }
      router.push(nextUrl);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "无法继续当前步骤，请重试。");
    } finally {
      setBusy(false);
    }
  }

  const controls: WorkflowStepControls = {
    apiUrl: API_BASE_URL,
    busy,
    refresh,
    setNextReady,
    setNextAction,
    setStepError,
  };

  return (
    <WorkflowShell
      profileId={profileId}
      currentStep={currentStep}
      snapshot={snapshot}
      loading={loading}
      busy={busy}
      nextReady={nextReady}
      error={error}
      onNext={() => void handleNext()}
      onRetry={() => void loadWorkflow(true)}
    >
      {snapshot ? renderStep(snapshot, controls) : null}
    </WorkflowShell>
  );
}
