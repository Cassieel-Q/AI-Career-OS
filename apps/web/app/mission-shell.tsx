"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { MISSION_TABS, missionHref, missionTabLabel } from "./missions.ts";
import type { Mission, MissionTab } from "./missions.ts";
import { missionIdentityLabel, missionStatusLabel } from "./mission-state.ts";

type MissionShellProps = {
  mission: Mission;
  currentTab: MissionTab;
  children: ReactNode;
  compactHints?: string[];
};

export function MissionShell({ mission, currentTab, children, compactHints = [] }: MissionShellProps) {
  const router = useRouter();
  return (
    <main className="mission-shell mission-shell-compact">
      <header className="workflow-header mission-topbar">
        <Link className="button-secondary mission-back" href="/missions">
          ← 我的岗位
        </Link>
        <div className="mission-topbar-title">
          <strong>
            {missionIdentityLabel(mission)}
          </strong>
          <span className="mission-status-badge">{missionStatusLabel(mission.status)}</span>
        </div>
      </header>
      <div className="mission-layout">
        <aside className="mission-sidebar">
          <nav aria-label="准备步骤">
            <ol className="mission-tab-list">
              {MISSION_TABS.map((tab) => (
                <li key={tab} className={tab === currentTab ? "mission-tab current" : "mission-tab"}>
                  <button
                    type="button"
                    aria-current={tab === currentTab ? "page" : undefined}
                    onClick={() => router.push(missionHref(mission.id, tab))}
                  >
                    <span className="mission-tab-marker" aria-hidden="true">
                      {tab === currentTab ? "●" : "○"}
                    </span>
                    {missionTabLabel(tab)}
                  </button>
                </li>
              ))}
            </ol>
          </nav>
          {compactHints.length > 0 && (
            <ul className="mission-compact-hints">
              {compactHints.map((hint) => (
                <li key={hint}>{hint}</li>
              ))}
            </ul>
          )}
        </aside>
        <section className="mission-main" aria-label={missionTabLabel(currentTab)}>
          {children}
        </section>
      </div>
    </main>
  );
}
