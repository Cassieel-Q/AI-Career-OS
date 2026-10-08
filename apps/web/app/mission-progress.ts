import { MISSION_STAGE_LABELS } from "./mission-copy.ts";
import { missionHref } from "./missions.ts";
import type { Route } from "next";

export type ProgressStage = "role" | "resume" | "interview" | "outcome";
export type ProgressStatus = "complete" | "current" | "available" | "locked";
export type ProgressStep = {
  key: ProgressStage;
  label: string;
  status: ProgressStatus;
  href: Route;
  reason?: string;
};

export type MissionProgressInput = {
  missionId: string;
  workflowState?: string | null;
  currentTab: ProgressStage;
  resumeBound: boolean;
  targetConfirmed: boolean;
  sessionStatus?: string | null;
};

const STAGES: readonly ProgressStage[] = ["role", "resume", "interview", "outcome"];

/** All unlocks come from persisted API data passed by the page or shell. */
export function deriveMissionProgress(input: MissionProgressInput): ProgressStep[] {
  const state = String(input.workflowState ?? "").toUpperCase();
  const roleReady = !["", "JD_REQUIRED", "JOB_ANALYZING"].includes(state);
  const resumeReady = input.targetConfirmed;
  const interviewDone = input.sessionStatus === "COMPLETED";
  const open = [true, roleReady, resumeReady, interviewDone];
  const completed = [roleReady, resumeReady, interviewDone, state === "OUTCOME"];
  const reasons = ["", "先保存岗位信息。", "先确认最终简历。", "先完成模拟面试。"];

  return STAGES.map((key, index) => {
    const status: ProgressStatus = !open[index]
      ? "locked"
      : input.currentTab === key
        ? "current"
        : completed[index]
          ? "complete"
          : "available";
    return {
      key,
      label: MISSION_STAGE_LABELS[index],
      status,
      href: missionHref(input.missionId, key),
      ...(status === "locked" ? { reason: reasons[index] } : {}),
    };
  });
}
