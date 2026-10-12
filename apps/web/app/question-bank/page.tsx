"use client";

import Link from "next/link";
import type { Route } from "next";
import { useCallback, useEffect, useMemo, useState } from "react";

import { readAssistantContext } from "../assistant-context.ts";
import { fetchPlaza, readCurrentProfileId, type PlazaItem } from "../career-hub.ts";
import {
  INTERVIEW_ROUNDS,
  listInterviewRecords,
  type InterviewRecordCompanyGroup,
  type InterviewRound,
} from "../interview-records.ts";
import {
  QUESTION_CATEGORIES,
  QUESTION_CATEGORY_LABEL,
  QUESTION_DIFFICULTIES,
  QUESTION_DIFFICULTY_LABEL,
  addQuestionItem,
  createQuestionBank,
  createRealQuestion,
  explainQuestion,
  fetchResumeSuggestions,
  generateQuestionBank,
  generateReferenceAnswer,
  isUngroundedAnswer,
  listQuestionBanks,
  type QuestionBank,
  type QuestionCategory,
  type QuestionDifficulty,
  type QuestionItem,
  type ResumeSuggestion,
} from "../question-bank.ts";

type CategoryFilter = "ALL" | QuestionCategory;
type Tab = "prepare" | "records";

const CATEGORY_FILTERS: CategoryFilter[] = ["ALL", ...QUESTION_CATEGORIES];

type SessionOption = { key: string; missionId: string; company: string; role: string };

export default function QuestionBankPage() {
  const [tab, setTab] = useState<Tab>("prepare");
  const [profileId, setProfileId] = useState("");
  const [error, setError] = useState("");

  // ---- 题库（原「题库」页能力，整体保留）----
  const [banks, setBanks] = useState<QuestionBank[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState("");
  const [filter, setFilter] = useState<CategoryFilter>("ALL");
  const [bankName, setBankName] = useState("我的题库");
  const [newQuestion, setNewQuestion] = useState("");
  const [newCategory, setNewCategory] = useState<QuestionCategory>("BASIC");
  const [newDifficulty, setNewDifficulty] = useState<QuestionDifficulty>("MEDIUM");
  const [newStyle, setNewStyle] = useState("");
  const [asReal, setAsReal] = useState(false);
  const [suggestions, setSuggestions] = useState<Record<string, ResumeSuggestion[]>>({});

  // ---- 面试场次：公司 / 岗位 + 第几次面试 ----
  const [missions, setMissions] = useState<PlazaItem[]>([]);
  const [sessionKey, setSessionKey] = useState("");
  const [round, setRound] = useState<InterviewRound>("一面");

  // ---- 面试记录（原「面试」页能力）----
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [companies, setCompanies] = useState<InterviewRecordCompanyGroup[]>([]);

  const loadBanks = useCallback(async (pid: string) => {
    if (!pid) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setBanks(await listQuestionBanks(pid));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取题库失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const plaza = await fetchPlaza();
      setMissions(plaza.items ?? []);
    } catch {
      setMissions([]);
    }
  }, []);

  const loadRecords = useCallback(async (pid: string) => {
    if (!pid) {
      setCompanies([]);
      return;
    }
    setRecordsLoading(true);
    try {
      const data = await listInterviewRecords(pid);
      setCompanies(data.companies || []);
    } catch (caught) {
      setCompanies([]);
      setError(caught instanceof Error ? caught.message : "读取面试记录失败。");
    } finally {
      setRecordsLoading(false);
    }
  }, []);

  useEffect(() => {
    const pid = readCurrentProfileId();
    setProfileId(pid);
    void loadBanks(pid);
    void loadSessions();
  }, [loadBanks, loadSessions]);

  // 旧「面试」入口 (/interview-records) 会带着 ?tab=records 跳过来。
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (new URLSearchParams(window.location.search).get("tab") === "records") setTab("records");
  }, []);

  useEffect(() => {
    if (tab === "records") void loadRecords(profileId);
  }, [loadRecords, profileId, tab]);

  const items = useMemo(() => {
    const all = banks.flatMap((bank) => bank.items);
    return filter === "ALL" ? all : all.filter((item) => item.category === filter);
  }, [banks, filter]);

  // 场次候选：岗位广场（跨档案）按「公司 + 岗位」去重。
  const sessionOptions = useMemo<SessionOption[]>(() => {
    const seen = new Map<string, SessionOption>();
    for (const item of missions) {
      const company = (item.company || "").trim();
      const role = (item.role || "").trim();
      if (!company) continue;
      const key = `${company}|${role}`;
      if (!seen.has(key)) seen.set(key, { key, missionId: item.mission_id, company, role });
    }
    return Array.from(seen.values());
  }, [missions]);

  const activeSession = sessionOptions.find((option) => option.key === sessionKey) ?? null;
  const activeBankId = banks[0]?.id ?? "";
  const newRecordHref = `/interview-records/new?company=${encodeURIComponent(activeSession?.company ?? "")}&round=${encodeURIComponent(round)}` as Route;

  const handleCreateBank = useCallback(async () => {
    if (!profileId || !bankName.trim()) return;
    setBusyId("new-bank");
    try {
      await createQuestionBank(profileId, bankName.trim(), activeSession?.missionId ?? null);
      await loadBanks(profileId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建题库失败。");
    } finally {
      setBusyId("");
    }
  }, [activeSession?.missionId, bankName, loadBanks, profileId]);

  // 第六阶段：按真实上下文（JD + 已确认岗位简历）生成三分类题库。
  // 优先用本页选中的场次，其次回落到顺顺登记的上下文。
  const handleGenerateFromContext = useCallback(async () => {
    if (!profileId) return;
    setBusyId("generate");
    try {
      const context = readAssistantContext();
      await generateQuestionBank(profileId, {
        mission_id: activeSession?.missionId || context.missionId,
        target_resume_id: context.targetResumeId,
      });
      await loadBanks(profileId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "按岗位生成题库失败。");
    } finally {
      setBusyId("");
    }
  }, [activeSession?.missionId, loadBanks, profileId]);

  const handleAddQuestion = useCallback(async () => {
    if (!profileId || !newQuestion.trim()) return;
    setBusyId("new-question");
    try {
      const payload = {
        question_text: newQuestion.trim(),
        category: newCategory,
        difficulty: newDifficulty,
        interviewer_style: newStyle.trim() || undefined,
        mission_id: activeSession?.missionId,
      };
      if (asReal) {
        await createRealQuestion(profileId, payload);
      } else {
        let bankId = activeBankId;
        if (!bankId) {
          const bank = await createQuestionBank(profileId, "我的题库", activeSession?.missionId ?? null);
          bankId = bank.id;
        }
        await addQuestionItem(bankId, {
          question_text: payload.question_text,
          category: payload.category,
          difficulty: payload.difficulty,
          interviewer_style: payload.interviewer_style,
          source: "MODEL",
        });
      }
      setNewQuestion("");
      await loadBanks(profileId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "添加题目失败。");
    } finally {
      setBusyId("");
    }
  }, [activeBankId, activeSession?.missionId, asReal, loadBanks, newCategory, newDifficulty, newQuestion, newStyle, profileId]);

  const handleReferenceAnswer = useCallback(
    async (item: QuestionItem) => {
      setBusyId(item.id);
      try {
        await generateReferenceAnswer(item.id);
        await loadBanks(profileId);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "生成参考答案失败。");
      } finally {
        setBusyId("");
      }
    },
    [loadBanks, profileId],
  );

  const handleSuggestions = useCallback(async (item: QuestionItem) => {
    setBusyId(item.id);
    try {
      setSuggestions((prev) => ({ ...prev, [item.id]: [] }));
      const result = await fetchResumeSuggestions(item.id);
      setSuggestions((prev) => ({ ...prev, [item.id]: result }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "获取简历优化建议失败。");
    } finally {
      setBusyId("");
    }
  }, []);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Interview Bank</p>
          <h1 className="app-page-title">面试题库</h1>
          <p className="app-page-subtitle">先按「公司 + 第几次面试」定好场次，再准备题目、记录真实被问到的问题。</p>
        </div>
      </header>

      {error && <p className="app-inline-error" role="alert">{error}</p>}

      {!profileId && !loading ? (
        <section className="app-card app-empty">还没有简历档案，请先上传简历后再建题库。</section>
      ) : (
        <>
          <section className="app-card session-bar" aria-label="面试场次">
            <label className="field-label">
              目标公司 / 岗位
              <select value={sessionKey} onChange={(event) => setSessionKey(event.target.value)}>
                <option value="">未指定（用顺顺当前上下文）</option>
                {sessionOptions.map((option) => (
                  <option key={option.key} value={option.key}>
                    {option.company}{option.role ? ` · ${option.role}` : ""}
                  </option>
                ))}
              </select>
            </label>
            <label className="field-label">
              第几次面试
              <select value={round} onChange={(event) => setRound(event.target.value as InterviewRound)}>
                {INTERVIEW_ROUNDS.map((value) => (
                  <option key={value} value={value}>{value}</option>
                ))}
              </select>
            </label>
            <Link className="app-btn primary" href={newRecordHref}>
              录入这场面试
            </Link>
          </section>

          <div className="session-tabs" role="tablist" aria-label="面试题库分区">
            <button
              type="button"
              role="tab"
              aria-selected={tab === "prepare"}
              className={tab === "prepare" ? "active" : ""}
              onClick={() => setTab("prepare")}
            >
              题目准备
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === "records"}
              className={tab === "records" ? "active" : ""}
              onClick={() => setTab("records")}
            >
              面试记录{companies.length ? `（${companies.length}）` : ""}
            </button>
          </div>

          {tab === "prepare" ? (
            <>
              <section className="app-card" aria-label="添加题目">
                <strong>添加题目</strong>
                <div className="layout-controls">
                  <label>
                    分类
                    <select value={newCategory} onChange={(event) => setNewCategory(event.target.value as QuestionCategory)}>
                      {QUESTION_CATEGORIES.map((value) => (
                        <option key={value} value={value}>{QUESTION_CATEGORY_LABEL[value]}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    难度
                    <select value={newDifficulty} onChange={(event) => setNewDifficulty(event.target.value as QuestionDifficulty)}>
                      {QUESTION_DIFFICULTIES.map((value) => (
                        <option key={value} value={value}>{QUESTION_DIFFICULTY_LABEL[value]}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    面试官风格（可选）
                    <input value={newStyle} onChange={(event) => setNewStyle(event.target.value)} placeholder="如：追问型 / 压力面" />
                  </label>
                  <label>
                    题库名（首次自动创建）
                    <input value={bankName} onChange={(event) => setBankName(event.target.value)} placeholder="我的题库" />
                  </label>
                </div>
                <textarea
                  className="app-textarea"
                  rows={3}
                  value={newQuestion}
                  onChange={(event) => setNewQuestion(event.target.value)}
                  placeholder="输入题目，例如：讲一个你做过的失败项目，你怎么复盘的？"
                />
                <label className="app-checkbox">
                  <input type="checkbox" checked={asReal} onChange={(event) => setAsReal(event.target.checked)} />
                  这是真实面试被问到的题（记入真题）
                </label>
                <div className="mission-action-row">
                  <button type="button" className="app-btn" disabled={busyId === "new-question" || !newQuestion.trim()} onClick={() => void handleAddQuestion()}>
                    添加题目
                  </button>
                  <button type="button" className="app-btn" disabled={busyId === "new-bank"} onClick={() => void handleCreateBank()}>
                    新建题库
                  </button>
                  <button type="button" className="app-btn primary" disabled={busyId === "generate"} onClick={() => void handleGenerateFromContext()}>
                    {activeSession ? `按「${activeSession.company}」生成题库` : "按当前岗位生成题库"}
                  </button>
                </div>
              </section>

              <section className="app-card" aria-label="题目列表">
                <div className="question-card-head">
                  <strong>题目（{items.length}）</strong>
                  <div className="question-meta">
                    {CATEGORY_FILTERS.map((value) => (
                      <button
                        key={value}
                        type="button"
                        className={`app-chip${filter === value ? " filled" : ""}`}
                        onClick={() => setFilter(value)}
                      >
                        {value === "ALL" ? "全部" : QUESTION_CATEGORY_LABEL[value]}
                      </button>
                    ))}
                  </div>
                </div>

                {loading ? (
                  <p className="app-muted">正在读取题库…</p>
                ) : items.length === 0 ? (
                  <p className="app-muted">还没有题目，先在上方添加一道，或按当前岗位生成。</p>
                ) : (
                  <div className="question-bank-grid">
                    {items.map((item) => {
                      const answer = item.reference_answer;
                      const ungrounded = isUngroundedAnswer(answer);
                      const explain = explainQuestion(item);
                      return (
                        <article key={item.id} className="question-card">
                          <div className="question-card-head">
                            <span className="app-badge muted">{QUESTION_CATEGORY_LABEL[item.category as QuestionCategory] ?? item.category}</span>
                            <span className={`app-badge ${item.source === "REAL_INTERVIEW" ? "filled" : "muted"}`}>
                              {item.source === "REAL_INTERVIEW" ? "真题" : "练习"}
                            </span>
                          </div>
                          <p>{item.question_text}</p>
                          <div className="question-meta">
                            <span className="app-badge muted">{QUESTION_DIFFICULTY_LABEL[item.difficulty as QuestionDifficulty] ?? item.difficulty}</span>
                            {item.interviewer_style && <span className="app-badge muted">{item.interviewer_style}</span>}
                          </div>

                          <dl className="question-explain">
                            <dt>为什么问这题</dt>
                            <dd>{explain.why}</dd>
                            <dt>关联 JD 要求</dt>
                            <dd>{explain.jdRefs.length ? explain.jdRefs.join("；") : "未标注"}</dd>
                            <dt>用哪段经历回答</dt>
                            <dd>{explain.experienceRefs.length ? explain.experienceRefs.join("；") : "暂无带证据的经历"}</dd>
                            <dt>可以说的事实</dt>
                            <dd>{explain.allowedFacts.length ? explain.allowedFacts.join("；") : "暂无已确认事实"}</dd>
                            <dt>不能编造</dt>
                            <dd>{explain.notToInvent}</dd>
                          </dl>
                          {explain.followups.length ? (
                            <ul className="question-followups">
                              {explain.followups.map((followup, index) => (
                                <li key={`${item.id}-followup-${index}`}>可能追问：{followup}</li>
                              ))}
                            </ul>
                          ) : null}

                          {answer ? (
                            <div className={`question-answer${ungrounded ? " grounded-unknown" : ""}`}>
                              {ungrounded && <strong>事实不足，未编造答案：</strong>}
                              {answer.answer_text}
                              <div className="question-meta">
                                <span className="app-badge muted">接地：{answer.grounding}</span>
                              </div>
                            </div>
                          ) : (
                            <p className="app-muted">还没有参考答案。</p>
                          )}
                          {suggestions[item.id]?.length ? (
                            <ul className="app-list">
                              {suggestions[item.id].map((s, index) => (
                                <li key={`${item.id}-${index}`}>
                                  <strong>{s.kind}</strong>：{s.suggestion}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                          <div className="mission-action-row">
                            <button type="button" className="app-btn" disabled={busyId === item.id} onClick={() => void handleReferenceAnswer(item)}>
                              生成参考答案
                            </button>
                            <button type="button" className="app-btn" disabled={busyId === item.id} onClick={() => void handleSuggestions(item)}>
                              简历优化建议
                            </button>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                )}
              </section>
            </>
          ) : (
            <section className="app-card" aria-label="按公司分组的面试记录">
              <div className="question-card-head">
                <strong>面试记录</strong>
                <Link className="app-btn" href={newRecordHref}>新建录入</Link>
              </div>
              {recordsLoading ? (
                <p className="app-muted">读取中…</p>
              ) : companies.length ? (
                <div className="session-record-list">
                  {companies.map((group) => (
                    <Link
                      key={group.company_key}
                      className="session-record-item"
                      href={`/interview-records/company/${group.company_key}` as Route}
                    >
                      <span className="session-record-main">
                        <strong>{group.company}</strong>
                        <small>
                          {group.record_count} 场
                          {group.latest_interviewed_on ? ` · 最近 ${group.latest_interviewed_on}` : ""}
                          {group.rounds.length ? ` · ${group.rounds.join(" / ")}` : ""}
                        </small>
                      </span>
                      <span className="app-badge muted">打开</span>
                    </Link>
                  ))}
                </div>
              ) : (
                <p className="app-muted">还没有面试记录。先在上面选好场次，再点「录入这场面试」。</p>
              )}
            </section>
          )}
        </>
      )}
    </main>
  );
}
