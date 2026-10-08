"use client";

import Link from "next/link";
import type { ProgressStep } from "./mission-progress.ts";

export function MissionProgress({ steps }: { steps: ProgressStep[] }) {
  return (
    <nav className="mission-progress" aria-label="岗位进度">
      <ol className="mission-progress-list">
        {steps.map((step, index) => (
          <li className={`mission-progress-item is-${step.status}`} key={step.key}>
            {step.status === "locked" ? (
              <div className="mission-progress-node" aria-disabled="true">
                <span className="mission-progress-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <span>{step.label}</span>
                <small>{step.reason}</small>
              </div>
            ) : step.status === "current" ? (
              <div className="mission-progress-node" aria-current="step">
                <span className="mission-progress-number" aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
                <span>{step.label}</span>
              </div>
            ) : (
              <Link className="mission-progress-node" href={step.href}>
                <span className="mission-progress-number" aria-hidden="true">{step.status === "complete" ? "✓" : String(index + 1).padStart(2, "0")}</span>
                <span>{step.label}</span>
                <span className="sr-only">{step.status === "complete" ? "已完成，可返回" : "可进入"}</span>
              </Link>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
