"use client";

/**
 * Evidence OS — 8-step Multi-JD workflow skeleton.
 * Wires to /evidence-os/* FastAPI routes. Additive; does not replace existing proof flow.
 */

import { useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

const STEPS = [
  "Intake / Evidence",
  "Claims",
  "Ingest JD",
  "Match & Gap",
  "Position & Draft",
  "Claim Audit",
  "Approve",
  "Render & Eval",
] as const;

type Json = Record<string, unknown>;

async function api<T = Json>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(JSON.stringify(data?.detail || data || res.statusText));
  return data as T;
}

export default function EvidenceOsPage() {
  const [step, setStep] = useState(0);
  const [profileId, setProfileId] = useState("");
  const [log, setLog] = useState<string>("");
  const [evidenceFact, setEvidenceFact] = useState("");
  const [claimWording, setClaimWording] = useState("");
  const [claimFact, setClaimFact] = useState("");
  const [evidenceId, setEvidenceId] = useState("");
  const [jdText, setJdText] = useState("");
  const [jdId, setJdId] = useState("");
  const [matchSummary, setMatchSummary] = useState("");
  const [versionId, setVersionId] = useState("");
  const [versionHash, setVersionHash] = useState("");
  const [draftText, setDraftText] = useState("");
  const [busy, setBusy] = useState(false);

  const title = useMemo(() => STEPS[step], [step]);

  function note(msg: string) {
    setLog((prev) => `${new Date().toLocaleTimeString()}  ${msg}\n${prev}`);
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      note(`ERROR: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main style={{ maxWidth: 920, margin: "40px auto", padding: 16, fontFamily: "system-ui" }}>
      <h1>Evidence OS (Advanced / Debug)</h1><p style={{color:'#a00'}}>Not the primary Job Mission path. Use Missions for dogfood.</p>
      <p style={{ color: "#555" }}>
        Evidence → Claim → Positioning → Writing. Confirmed-only finals. No metric estimates. Heuristic evals only.
      </p>

      <label>
        Profile ID{" "}
        <input
          value={profileId}
          onChange={(e) => setProfileId(e.target.value)}
          style={{ width: "100%", marginBottom: 12 }}
          placeholder="user_profiles.id UUID"
        />
      </label>

      <nav style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 16 }}>
        {STEPS.map((s, i) => (
          <button
            key={s}
            type="button"
            onClick={() => setStep(i)}
            style={{
              padding: "6px 10px",
              borderRadius: 6,
              border: i === step ? "2px solid #111" : "1px solid #ccc",
              background: i === step ? "#111" : "#fff",
              color: i === step ? "#fff" : "#111",
            }}
          >
            {i + 1}. {s}
          </button>
        ))}
      </nav>

      <section style={{ border: "1px solid #ddd", borderRadius: 8, padding: 16, marginBottom: 16 }}>
        <h2>
          Step {step + 1}: {title}
        </h2>

        {step === 0 && (
          <div>
            <textarea
              rows={4}
              value={evidenceFact}
              onChange={(e) => setEvidenceFact(e.target.value)}
              placeholder="Immutable fact text (no estimated metrics)"
              style={{ width: "100%" }}
            />
            <button
              disabled={busy || !profileId}
              type="button"
              onClick={() =>
                run(async () => {
                  const ev = await api(`/evidence-os/profiles/${profileId}/evidence`, {
                    method: "POST",
                    body: JSON.stringify({
                      fact_text: evidenceFact,
                      evidence_type: "user_confirmed",
                      source_ids: [],
                    }),
                  });
                  setEvidenceId(String(ev.id));
                  note(`Evidence created: ${ev.id}`);
                  setStep(1);
                })
              }
            >
              Save evidence
            </button>
          </div>
        )}

        {step === 1 && (
          <div>
            <input
              value={claimFact}
              onChange={(e) => setClaimFact(e.target.value)}
              placeholder="source_fact"
              style={{ width: "100%", marginBottom: 8 }}
            />
            <textarea
              rows={3}
              value={claimWording}
              onChange={(e) => setClaimWording(e.target.value)}
              placeholder="candidate_wording"
              style={{ width: "100%" }}
            />
            <p style={{ fontSize: 13 }}>Evidence ID: {evidenceId || "(paste/create first)"}</p>
            <button
              disabled={busy || !profileId || !evidenceId}
              type="button"
              onClick={() =>
                run(async () => {
                  const c = await api(`/evidence-os/profiles/${profileId}/claims`, {
                    method: "POST",
                    body: JSON.stringify({
                      source_fact: claimFact || evidenceFact,
                      candidate_wording: claimWording,
                      verification_status: "confirmed",
                      responsibility_level: "owned_module",
                      boundary: "Owned module delivery; not company-wide P&L.",
                      evidence_ids: [evidenceId],
                      competency_ids: ["rag", "model_evaluation"],
                    }),
                  });
                  note(`Claim created: ${c.id}`);
                  setStep(2);
                })
              }
            >
              Create confirmed claim
            </button>
          </div>
        )}

        {step === 2 && (
          <div>
            <textarea
              rows={8}
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="Paste JD text..."
              style={{ width: "100%" }}
            />
            <button
              disabled={busy || !profileId || !jdText}
              type="button"
              onClick={() =>
                run(async () => {
                  const jd = await api(`/evidence-os/profiles/${profileId}/jds`, {
                    method: "POST",
                    body: JSON.stringify({ title: "Target role", raw_text: jdText, language: "en" }),
                  });
                  setJdId(String(jd.id));
                  note(`JD ingested: ${jd.id} with ${(jd.requirements as unknown[])?.length || 0} requirements`);
                  setStep(3);
                })
              }
            >
              Ingest JD
            </button>
          </div>
        )}

        {step === 3 && (
          <div>
            <p>JD: {jdId || "—"}</p>
            <button
              disabled={busy || !profileId || !jdId}
              type="button"
              onClick={() =>
                run(async () => {
                  const m = await api(`/evidence-os/profiles/${profileId}/jds/${jdId}/match`, {
                    method: "POST",
                  });
                  setMatchSummary(
                    `covered=${m.covered} weak=${m.weak} missing=${m.missing} needs_excavation=${m.needs_excavation}`
                  );
                  note(`Match: ${JSON.stringify(m)}`);
                  setStep(4);
                })
              }
            >
              Run match & gap
            </button>
            {matchSummary && <pre>{matchSummary}</pre>}
          </div>
        )}

        {step === 4 && (
          <div>
            <button
              disabled={busy || !profileId || !jdId}
              type="button"
              onClick={() =>
                run(async () => {
                  const v = await api(`/evidence-os/profiles/${profileId}/position`, {
                    method: "POST",
                    body: JSON.stringify({ jd_id: jdId, positioning_mode: "conservative" }),
                  });
                  setVersionId(String(v.id));
                  setVersionHash(String(v.full_text_hash || ""));
                  setDraftText(String(v.full_text || ""));
                  note(`Draft version: ${v.id}`);
                  setStep(5);
                })
              }
            >
              Position & draft (confirmed only)
            </button>
            {draftText && <pre style={{ whiteSpace: "pre-wrap" }}>{draftText}</pre>}
          </div>
        )}

        {step === 5 && (
          <div>
            <button
              disabled={busy || !versionId}
              type="button"
              onClick={() =>
                run(async () => {
                  const a = await api(`/evidence-os/versions/${versionId}/audit`, { method: "POST" });
                  note(`Audit: ${JSON.stringify(a)}`);
                  const v = await api(`/evidence-os/versions/${versionId}`);
                  setVersionHash(String(v.full_text_hash || ""));
                  setDraftText(String(v.full_text || ""));
                  if (a.audit_safe) setStep(6);
                })
              }
            >
              Run claim audit
            </button>
          </div>
        )}

        {step === 6 && (
          <div>
            <p style={{ fontSize: 13 }}>Hash: {versionHash}</p>
            <button
              disabled={busy || !versionId || !versionHash}
              type="button"
              onClick={() =>
                run(async () => {
                  const a = await api(`/evidence-os/versions/${versionId}/approve`, {
                    method: "POST",
                    body: JSON.stringify({ full_text_hash: versionHash }),
                  });
                  note(`Approved: ${a.id}`);
                  setStep(7);
                })
              }
            >
              Approve (hash-bound)
            </button>
          </div>
        )}

        {step === 7 && (
          <div>
            <button
              disabled={busy || !versionId}
              type="button"
              onClick={() =>
                run(async () => {
                  const r = await api(`/evidence-os/versions/${versionId}/render`, { method: "POST" });
                  note(`Render: ${r.message}`);
                  const e = await api(`/evidence-os/versions/${versionId}/evals`, { method: "POST" });
                  note(`Heuristic evals: ${JSON.stringify(e)}`);
                })
              }
            >
              Render + heuristic evals
            </button>
          </div>
        )}
      </section>

      <pre
        style={{
          background: "#f6f6f6",
          padding: 12,
          borderRadius: 8,
          maxHeight: 240,
          overflow: "auto",
          fontSize: 12,
        }}
      >
        {log || "Activity log…"}
      </pre>
    </main>
  );
}

