"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { fetchClaims, readCurrentProfileId, type ClaimsRead } from "../career-hub.ts";
import { isUnknownIdentity } from "../mission-state.ts";

const READY_SET = new Set(["READY", "CONFIRMED", "SUPPORTED"]);
const NEEDS_SET = new Set(["NEEDS_CONFIRMATION", "UNSUPPORTED", "NEEDS_EVIDENCE"]);

function claimStatus(status: string): { label: string; cls: string } {
  const s = (status || "").toUpperCase();
  if (READY_SET.has(s)) return { label: "已确认", cls: "filled" };
  if (NEEDS_SET.has(s)) return { label: "待核对", cls: "attention" };
  return { label: status || "未定", cls: "muted" };
}

export default function ClaimsPage() {
  const [profileId] = useState<string>(readCurrentProfileId());
  const [claims, setClaims] = useState<ClaimsRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const pid = readCurrentProfileId();
    if (!pid) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setClaims(await fetchClaims(pid));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取事实核对失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Claims</p>
          <h1 className="app-page-title">事实核对</h1>
          <p className="app-page-subtitle">只有确认过的事实才会写进简历，未确认的显式避开。</p>
        </div>
      </header>

      {error ? <p className="message error" role="alert">{error}</p> : null}

      <section className="app-stat-grid" aria-label="台账概览">
        <div className="app-stat-card"><div className="app-stat-value">{claims?.total ?? 0}</div><div className="app-stat-label">主张条目</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{claims?.confirmed ?? 0}</div><div className="app-stat-label">已确认</div></div>
        <div className="app-stat-card"><div className="app-stat-value">{claims?.needs_confirmation ?? 0}</div><div className="app-stat-label">待核对</div></div>
      </section>

      {loading ? (
        <div className="app-empty">读取中…</div>
      ) : !profileId ? (
        <div className="app-empty">
          还没有简历档案。请先
          <Link className="app-btn primary" href="/workflow/start" style={{ margin: "0 0.5rem" }}>上传简历</Link>
        </div>
      ) : claims?.claims.length ? (
        claims.claims.map((claim) => {
          const status = claimStatus(claim.readiness_status);
          return (
            <article key={claim.id} className="app-card claim-card">
              <header className="claim-card-header">
                <div>
                  <div className="app-card-title">
                    {isUnknownIdentity(claim.company) ? "未知公司" : claim.company}
                    {isUnknownIdentity(claim.role) ? "" : ` · ${claim.role}`}
                  </div>
                  <div className="app-card-meta">
                    置信度 {Math.round(claim.confidence * 100)}%
                    {claim.evidence_refs.length ? ` · ${claim.evidence_refs.length} 条证据` : " · 无证据"}
                  </div>
                </div>
                <span className={`app-badge ${status.cls}`}>{status.label}</span>
              </header>
              <p className="claim-text">{claim.claim}</p>
              {claim.risk_reason ? <p className="claim-risk">风险提示：{claim.risk_reason}</p> : null}
            </article>
          );
        })
      ) : (
        <div className="app-empty">还没有事实条目。完成岗位分析后，主张会自动沉淀到这里。</div>
      )}
    </main>
  );
}
