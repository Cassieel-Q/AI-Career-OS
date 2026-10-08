"use client";

import { taskProgressRows } from "./task-progress.ts";
import type { TaskKind } from "./task-progress.ts";

export function TaskProgress({ kind, activeIndex, error, onRetry }: {
  kind: TaskKind;
  activeIndex: number;
  error?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="task-progress" role={error ? "alert" : "status"} aria-live="polite">
      <ol>
        {taskProgressRows(kind, activeIndex).map((row) => (
          <li className={`task-progress-${row.status}`} key={row.label}>
            <span aria-hidden="true">{row.status === "done" ? "✓" : row.status === "active" ? "■" : "□"}</span>
            <span>{row.label}</span>
          </li>
        ))}
      </ol>
      {error && <div className="task-progress-error"><span>{error}</span>{onRetry && <button type="button" className="button-secondary" onClick={onRetry}>重新生成</button>}</div>}
    </div>
  );
}
