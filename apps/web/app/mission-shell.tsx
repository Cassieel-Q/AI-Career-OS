"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { missionTabLabel } from "./missions.ts";
import type { Mission, MissionTab } from "./missions.ts";
import { missionIdentityLabel, missionStatusLabel } from "./mission-state.ts";
import { MissionProgress } from "./mission-progress.tsx";
import type { ProgressStep } from "./mission-progress.ts";

type MissionShellProps = {
  mission: Mission;
  currentTab: MissionTab;
  children: ReactNode;
  compactHints?: string[];
  progressSteps: ProgressStep[];
};

export function MissionShell({ mission, currentTab, children, compactHints = [], progressSteps }: MissionShellProps) {
  return (
    <main className="mission-shell mission-shell-compact">
      <header className="workflow-header mission-topbar">
        <Link className="button-secondary mission-back" href="/missions">
          ← 岗位档案
        </Link>
        <div className="mission-topbar-title">
          <strong>
            {missionIdentityLabel(mission)}
          </strong>
          <span className="mission-status-badge">{missionStatusLabel(mission.status)}</span>
        </div>
      </header>
      <MissionProgress steps={progressSteps} />
      <div className="mission-layout">
        {compactHints.length > 0 && <p className="mission-compact-hints">{compactHints[0]}</p>}
        <section className="mission-main" aria-label={missionTabLabel(currentTab)}>
          {children}
        </section>
      </div>
    </main>
  );
}
