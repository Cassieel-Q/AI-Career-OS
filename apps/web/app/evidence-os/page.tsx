"use client";

/**
 * 证据库（Evidence OS）— 8 步证据 → 主张 → 定位 → 成稿工作流。
 * 对接 /evidence-os/* 后端路由；作为主岗位流程之外的进阶工具保留。
 */

import { useMemo, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

const STEPS = [
  { key: "evidence", label: "录入证据" },
  { key: "claims", label: "建立主张" },
  { key: "jd", label: "解析岗位" },
  { key: "match", label: "匹配差距" },
  { key: "draft", label: "定位成稿" },
  { key: "audit", label: "主张审计" },
  { key: "approve", label: "确认定稿" },
  { key: "render", label: "渲染评估" },
] as const;

type Json = Record<string, unknown>;

type RequirementOut = { id: string; raw_text: string; priority: string };

type MatchRowOut = {
  requirement_id: string;
  match_status: string;
  rationale: string;
  excavation_questions: string[];
};

type MatchResult = {
  covered: number;
  weak: number;
  missing: number;
  needs_excavation: number;
  rows: MatchRowOut[];
  admission: string;
  admission_reason: string;
  ref_score: number | null;
  ref_score_breakdown: { name: string; detail: string }[];
  disclaimer: string;
};

// 五类结论与准入建议的中文名映射：只做展示层，不改后端枚举值。
const MATCH_STATUS_LABEL: Record<string, string> = {
  covered: "已匹配",
  weak: "表达缺口",
  missing: "真实缺口",
  not_applicable: "不适用",
  needs_excavation: "待确认",
};

const ADMISSION_LABEL: Record<string, string> = {
  can_apply: "可以投递",
  confirm: "先确认再投",
  do_not_apply: "暂不建议投递",
  pending: "待评估",
};

async function api<T = Json>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(JSON.stringify(data?.detail || data || res.statusText));
  return data as T;
}

function StepIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 3.5h9L18 6.5V20a.8.8 0 0 1-.8.8H6.8A.8.8 0 0 1 6 20z" />
      <path d="M15 3.5v3h3M9 12h6M9 15.5h6" />
    </svg>
  );
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
  const [jdReqs, setJdReqs] = useState<RequirementOut[]>([]);
  const [matchResult, setMatchResult] = useState<MatchResult | null>(null);
  const [versionId, setVersionId] = useState("");
  const [versionHash, setVersionHash] = useState("");
  const [draftText, setDraftText] = useState("");
  const [busy, setBusy] = useState(false);

  const title = useMemo(() => STEPS[step].label, [step]);

  function note(msg: string) {
    setLog((prev) => `${new Date().toLocaleTimeString()}  ${msg}\n${prev}`);
  }

  function requirementText(requirementId: string): string {
    return jdReqs.find((item) => item.id === requirementId)?.raw_text || "（未找到对应要求原文）";
  }

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      note(`错误：${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">工具</p>
          <h1 className="app-page-title">证据库</h1>
          <p className="app-page-subtitle">把你的每一段经历拆成「可引用的证据」，让简历和面试回答都有据可查。</p>
        </div>
        <span className="app-badge muted">进阶模式</span>
      </header>

      <section className="app-card app-guide-card app-guide-card-compact" aria-label="使用说明">
        <p>日常不必手动维护本页——上传简历时系统会自动沉淀证据。只有想手动补证据（项目数据、聊天记录摘录）或核验某条主张时，才需要按下面 8 步往下走；通常只用前 3 步。</p>
        <details>
          <summary>什么时候需要用到这一页？</summary>
          <p>面试官追问「这件事真是你做的吗」时，你需要拿出经得起追问的细节。证据库把经历原文拆成一条条不可变的证据事实，简历主张、面试回答都能引用它们。</p>
          <p>完整 8 步：录入证据 → 建立主张 → 解析岗位 → 运行匹配 → 定位缺口 → 生成要点 → 复核 → 成稿。日常走前 3 步即可。</p>
        </details>
      </section>

      <section className="app-card">
        <div className="start-card-head">
          <span className="start-card-icon" aria-hidden="true"><StepIcon /></span>
          <div>
            <h2>工作档案</h2>
            <p>本页操作都围绕一个档案进行，先填入档案 ID</p>
          </div>
        </div>
        <div className="evidence-profile-row">
          <input
            className="start-select"
            value={profileId}
            onChange={(e) => setProfileId(e.target.value)}
            placeholder="档案 ID（user_profiles.id）"
            aria-label="档案 ID"
          />
        </div>
      </section>

      <nav className="app-filter-row" aria-label="工作流步骤">
        {STEPS.map((s, i) => (
          <button
            key={s.key}
            type="button"
            className={`app-filter${i === step ? " active" : ""}`}
            onClick={() => setStep(i)}
          >
            {i + 1}. {s.label}
          </button>
        ))}
      </nav>

      <section className="app-card">
        <div className="start-card-head">
          <div>
            <h2>第 {step + 1} 步 · {title}</h2>
          </div>
        </div>

        {step === 0 && (
          <div className="evidence-body">
            <textarea
              className="start-select evidence-area"
              rows={4}
              value={evidenceFact}
              onChange={(e) => setEvidenceFact(e.target.value)}
              placeholder="填写不可变的事实原文（不做任何数据估算）"
            />
            <button
              className="app-btn primary"
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
                  note(`证据已录入：${ev.id}`);
                  setStep(1);
                })
              }
            >
              保存证据
            </button>
          </div>
        )}

        {step === 1 && (
          <div className="evidence-body">
            <input
              className="start-select"
              value={claimFact}
              onChange={(e) => setClaimFact(e.target.value)}
              placeholder="来源事实（source_fact）"
            />
            <textarea
              className="start-select evidence-area"
              rows={3}
              value={claimWording}
              onChange={(e) => setClaimWording(e.target.value)}
              placeholder="简历表述（candidate_wording）"
            />
            <p className="start-note">证据 ID：{evidenceId || "（请先在第 1 步录入或粘贴）"}</p>
            <button
              className="app-btn primary"
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
                      boundary: "仅限本人负责的模块交付，不代表公司整体业绩。",
                      evidence_ids: [evidenceId],
                      competency_ids: ["rag", "model_evaluation"],
                    }),
                  });
                  note(`主张已建立：${c.id}`);
                  setStep(2);
                })
              }
            >
              建立已确认主张
            </button>
          </div>
        )}

        {step === 2 && (
          <div className="evidence-body">
            <textarea
              className="start-select evidence-area"
              rows={8}
              value={jdText}
              onChange={(e) => setJdText(e.target.value)}
              placeholder="粘贴完整岗位描述（JD）…"
            />
            <button
              className="app-btn primary"
              disabled={busy || !profileId || !jdText}
              type="button"
              onClick={() =>
                run(async () => {
                  const jd = await api(`/evidence-os/profiles/${profileId}/jds`, {
                    method: "POST",
                    body: JSON.stringify({ title: "目标岗位", raw_text: jdText, language: "en" }),
                  });
                  setJdId(String(jd.id));
                  setJdReqs((jd.requirements as RequirementOut[]) || []);
                  setMatchResult(null);
                  note(`岗位已解析：${jd.id}，共 ${(jd.requirements as unknown[])?.length || 0} 条要求`);
                  setStep(3);
                })
              }
            >
              解析岗位
            </button>
          </div>
        )}

        {step === 3 && (
          <div className="evidence-body">
            <p className="start-note">岗位 ID：{jdId || "—"}</p>
            <button
              className="app-btn primary"
              disabled={busy || !profileId || !jdId}
              type="button"
              onClick={() =>
                run(async () => {
                  const m = await api<MatchResult>(`/evidence-os/profiles/${profileId}/jds/${jdId}/match`, {
                    method: "POST",
                  });
                  setMatchResult(m);
                  note(`匹配完成：${ADMISSION_LABEL[m.admission] || m.admission} · 参考分 ${m.ref_score}`);
                })
              }
            >
              运行匹配与差距分析
            </button>

            {matchResult && (
              <div className="match-result">
                <div className="match-result-head">
                  <span className={`app-badge ${matchResult.admission === "do_not_apply" ? "attention" : "muted"}`}>
                    {ADMISSION_LABEL[matchResult.admission] || matchResult.admission}
                  </span>
                  <span className="match-score">
                    <b>{matchResult.ref_score ?? "—"}</b>
                    <small>参考分 / 100</small>
                  </span>
                </div>

                <p className="start-note">{matchResult.admission_reason}</p>
                <p className="start-note">
                  已匹配 {matchResult.covered} · 表达缺口 {matchResult.weak} · 真实缺口 {matchResult.missing} · 待确认{" "}
                  {matchResult.needs_excavation}
                </p>

                <ul className="match-rows">
                  {matchResult.rows.map((row) => (
                    <li key={row.requirement_id}>
                      <span className={`match-status ${row.match_status}`}>
                        {MATCH_STATUS_LABEL[row.match_status] || row.match_status}
                      </span>
                      <span className="match-rows-text">{requirementText(row.requirement_id)}</span>
                      {row.excavation_questions.length > 0 && (
                        <em className="match-rows-hint">深挖问题：{row.excavation_questions[0]}</em>
                      )}
                    </li>
                  ))}
                </ul>

                {matchResult.ref_score_breakdown.map((item) => (
                  <p className="start-note" key={item.name}>
                    · {item.name}：{item.detail}
                  </p>
                ))}
                <p className="start-note">{matchResult.disclaimer}</p>
                <p className="start-note">结论已生成。确认后点上方「5. 定位成稿」继续。</p>
              </div>
            )}
          </div>
        )}

        {step === 4 && (
          <div className="evidence-body">
            <button
              className="app-btn primary"
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
                  note(`定位稿已生成：${v.id}`);
                  setStep(5);
                })
              }
            >
              生成定位稿（仅含已确认主张）
            </button>
            {draftText && <pre className="evidence-log">{draftText}</pre>}
          </div>
        )}

        {step === 5 && (
          <div className="evidence-body">
            <button
              className="app-btn primary"
              disabled={busy || !versionId}
              type="button"
              onClick={() =>
                run(async () => {
                  const a = await api(`/evidence-os/versions/${versionId}/audit`, { method: "POST" });
                  note(`审计结果：${JSON.stringify(a)}`);
                  const v = await api(`/evidence-os/versions/${versionId}`);
                  setVersionHash(String(v.full_text_hash || ""));
                  setDraftText(String(v.full_text || ""));
                  if (a.audit_safe) setStep(6);
                })
              }
            >
              运行主张审计
            </button>
          </div>
        )}

        {step === 6 && (
          <div className="evidence-body">
            <p className="start-note">内容指纹：{versionHash || "—"}</p>
            <button
              className="app-btn primary"
              disabled={busy || !versionId || !versionHash}
              type="button"
              onClick={() =>
                run(async () => {
                  const a = await api(`/evidence-os/versions/${versionId}/approve`, {
                    method: "POST",
                    body: JSON.stringify({ full_text_hash: versionHash }),
                  });
                  note(`已确认：${a.id}`);
                  setStep(7);
                })
              }
            >
              确认定稿（指纹绑定）
            </button>
          </div>
        )}

        {step === 7 && (
          <div className="evidence-body">
            <button
              className="app-btn primary"
              disabled={busy || !versionId}
              type="button"
              onClick={() =>
                run(async () => {
                  const r = await api(`/evidence-os/versions/${versionId}/render`, { method: "POST" });
                  note(`渲染完成：${r.message}`);
                  const e = await api(`/evidence-os/versions/${versionId}/evals`, { method: "POST" });
                  note(`启发式评估：${JSON.stringify(e)}`);
                })
              }
            >
              渲染并运行启发式评估
            </button>
          </div>
        )}
      </section>

      <section className="app-card">
        <div className="start-card-head">
          <div>
            <h2>操作日志</h2>
            <p>每一步的结果与错误都会记录在这里</p>
          </div>
        </div>
        <pre className="evidence-log">{log || "暂无操作记录…"}</pre>
      </section>
    </main>
  );
}
