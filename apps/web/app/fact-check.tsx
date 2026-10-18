"use client";

/**
 * 事实核对面板（可信求职 v1.2 · 指令 1.4）。
 *
 * 「核对这段经历」展开后给出：原始文字、AI 建议表达、事实来源、已有哪些信息、
 * 还缺哪些信息，以及「确认属实 / 编辑事实 / 暂不使用」三个动作。
 *
 * 关键：确认动作只记录**用户明确核对**；系统提取到或用户采纳改写都不会自动变成已核实。
 */
import { useCallback, useEffect, useMemo, useState } from "react";

import { attestFact, FACT_STATUS_LABEL, readFacts, type FactItem, type FactList } from "./fact-trust.ts";
import {
  IMPACT_LABEL,
  impactSummary,
  readFactImpactByKey,
  syncFactToMission,
  type FactImpact,
} from "./fact-impact.ts";

const RISK_LABEL: Record<string, string> = {
  HIGH: "高风险：几乎没有可核对信息",
  MEDIUM: "中风险：还缺关键信息",
  LOW: "信息较完整",
};

export function FactCheckPanel({ profileId }: { profileId: string }) {
  const [data, setData] = useState<FactList | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [openKey, setOpenKey] = useState("");
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [syncSource, setSyncSource] = useState(false);
  const [busyKey, setBusyKey] = useState("");
  /** 这项事实被哪些岗位简历引用（只读影响面；更新必须由用户逐岗位点选）。 */
  const [impact, setImpact] = useState<FactImpact | null>(null);
  const [impactKey, setImpactKey] = useState("");
  const [syncingMission, setSyncingMission] = useState("");

  const loadImpact = useCallback(async (fact: FactItem) => {
    setImpact(null);
    setImpactKey(fact.fact_key);
    try {
      setImpact(await readFactImpactByKey(profileId, fact.fact_key));
    } catch {
      setImpact(null);
    }
  }, [profileId]);

  const load = useCallback(async () => {
    if (!profileId) {
      setData(null);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setData(await readFacts(profileId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取待核对事实失败。");
    } finally {
      setLoading(false);
    }
  }, [profileId]);

  useEffect(() => {
    void load();
  }, [load]);

  const facts = useMemo(() => data?.facts ?? [], [data]);
  const total = facts.length;
  const attested = data?.attested_count ?? 0;

  async function submit(fact: FactItem, status: "USER_ATTESTED" | "REJECTED" | "UNREVIEWED") {
    setBusyKey(fact.fact_key);
    setError("");
    setNotice("");
    try {
      await attestFact(profileId, {
        fact_key: fact.fact_key,
        status,
        fact_text: draft.trim() || undefined,
        note: note.trim() || undefined,
        apply_to_source: syncSource && status === "USER_ATTESTED" && draft.trim().length > 0,
      });
      setNotice(
        status === "USER_ATTESTED"
          ? "已记录：你确认这段内容属实。"
          : status === "REJECTED"
            ? "已标记为不属实，后续不会进入参考回答。"
            : "已撤回核对，这段内容回到待核对状态。",
      );
      setOpenKey("");
      setDraft("");
      setNote("");
      setSyncSource(false);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存核对结果失败。");
    } finally {
      setBusyKey("");
    }
  }

  function openFact(fact: FactItem) {
    setOpenKey(fact.fact_key);
    setDraft(fact.original_text);
    setNote(fact.note ?? "");
    setSyncSource(false);
    setNotice("");
    void loadImpact(fact);
  }

  async function syncMission(missionId: string) {
    if (!impact) return;
    setSyncingMission(missionId);
    setError("");
    try {
      const result = await syncFactToMission(profileId, impact.source_kind, impact.source_id, missionId);
      setNotice(result.message ?? "已同步到这一个岗位，其它岗位保持原版本。");
      await Promise.all([load(), loadImpact({ fact_key: impactKey } as FactItem)]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "同步到岗位简历失败。");
    } finally {
      setSyncingMission("");
    }
  }

  if (!profileId) return null;

  return (
    <section className="app-card fact-check">
      <div className="start-card-head">
        <div>
          <h2>事实核对</h2>
          <p>
            系统从简历里「提取到」不等于你「核实过」。这里逐条确认，确认过的事实才会用于生成参考回答与岗位简历。
          </p>
        </div>
      </div>

      {error ? <p className="message error" role="alert">{error}</p> : null}
      {notice ? <p className="message success" role="status">{notice}</p> : null}

      <p className="fact-check-progress" role="status">
        已确认 <strong>{attested}</strong> / {total} 条
        {data?.rejected_count ? ` · 已标记为不属实 ${data.rejected_count} 条` : ""}
      </p>

      {loading ? <div className="app-empty">读取中…</div> : null}
      {!loading && !total ? <div className="app-empty">这份档案还没有可核对的经历或技能。</div> : null}

      <ul className="fact-check-list">
        {facts.map((fact) => {
          const open = openKey === fact.fact_key;
          return (
            <li key={fact.fact_key} className="fact-check-item">
              <div className="fact-check-head">
                <div>
                  <span className="fact-check-title">{fact.title}</span>
                  <span className={`app-badge ${fact.verification_status === "USER_ATTESTED" ? "filled" : fact.verification_status === "REJECTED" ? "danger" : "muted"}`}>
                    {FACT_STATUS_LABEL[fact.verification_status]}
                  </span>
                  <span className="fact-check-risk">{RISK_LABEL[fact.risk] ?? ""}</span>
                </div>
                <button type="button" className="app-btn" onClick={() => (open ? setOpenKey("") : openFact(fact))}>
                  {open ? "收起" : "核对这段经历"}
                </button>
              </div>

              {!open ? (
                <p className="fact-check-preview">{fact.original_text || "（没有原文）"}</p>
              ) : (
                <div className="fact-check-body">
                  <div className="fact-check-block">
                    <span className="reference-label">原始文字</span>
                    <p>{fact.original_text || "（没有原文）"}</p>
                  </div>

                  {fact.suggested_text ? (
                    <div className="fact-check-block">
                      <span className="reference-label">AI 建议表达（采用它不等于核实事实）</span>
                      <p>{fact.suggested_text}</p>
                    </div>
                  ) : null}

                  <div className="fact-check-block">
                    <span className="reference-label">已有哪些信息</span>
                    <p>{fact.present_aspects.length ? fact.present_aspects.join("、") : "暂未识别到完整维度"}</p>
                  </div>

                  <div className="fact-check-block">
                    <span className="reference-label">还缺哪些信息</span>
                    <p>{fact.missing_aspects.length ? fact.missing_aspects.join("、") : "不缺，信息较完整"}</p>
                  </div>

                  <label className="field-label" htmlFor={`fact-draft-${fact.fact_key}`}>编辑事实（可选）</label>
                  <textarea
                    id={`fact-draft-${fact.fact_key}`}
                    className="textarea"
                    rows={4}
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    placeholder="按真实情况改写这段事实；不改动就留原样。"
                  />

                  <label className="fact-check-sync">
                    <input
                      type="checkbox"
                      checked={syncSource}
                      onChange={(event) => setSyncSource(event.target.checked)}
                    />
                    把修改后的内容同步回原始简历
                  </label>

                  <label className="field-label" htmlFor={`fact-note-${fact.fact_key}`}>备注（可选）</label>
                  <input
                    id={`fact-note-${fact.fact_key}`}
                    className="start-select"
                    value={note}
                    onChange={(event) => setNote(event.target.value)}
                    placeholder="例如：时间是 2024 年 3 月，不是 6 月"
                  />

                  {open && impact && impactKey === fact.fact_key && impact.total_missions > 0 ? (
                    <div className="fact-check-block fact-impact">
                      <span className="reference-label">这项事实还用在哪些岗位简历</span>
                      <p className="fact-impact-summary">{impactSummary(impact)}</p>
                      <p className="fact-impact-note">系统不会自动改动任何一份；你可以只更新需要的岗位。</p>
                      <ul className="fact-impact-list">
                        {impact.missions.map((mission) => (
                          <li key={mission.mission_id}>
                            <div>
                              <strong>{mission.display_name}</strong>
                              <span className={`app-badge ${mission.impact === "NONE" ? "muted" : "filled"}`}>
                                {IMPACT_LABEL[mission.impact]}
                              </span>
                              {mission.already_delivered ? <span className="app-badge danger">已投递</span> : null}
                              <small>修订版 v{mission.studio_revision}</small>
                            </div>
                            <button
                              type="button"
                              className="app-btn"
                              disabled={syncingMission === mission.mission_id || mission.impact === "NONE"}
                              onClick={() => void syncMission(mission.mission_id)}
                            >
                              {syncingMission === mission.mission_id ? "更新中…" : "只更新这一份"}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  <div className="start-row fact-check-actions">
                    <button
                      type="button"
                      className="app-btn primary"
                      disabled={busyKey === fact.fact_key}
                      onClick={() => void submit(fact, "USER_ATTESTED")}
                    >
                      确认属实
                    </button>
                    <button
                      type="button"
                      className="app-btn"
                      disabled={busyKey === fact.fact_key}
                      onClick={() => void submit(fact, "REJECTED")}
                    >
                      暂不使用
                    </button>
                    {fact.verification_status !== "UNREVIEWED" ? (
                      <button
                        type="button"
                        className="app-btn"
                        disabled={busyKey === fact.fact_key}
                        onClick={() => void submit(fact, "UNREVIEWED")}
                      >
                        撤回核对
                      </button>
                    ) : null}
                  </div>
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
