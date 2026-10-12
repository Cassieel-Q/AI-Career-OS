"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { readCurrentProfileId } from "../career-hub.ts";
import { readAssistantContext } from "../assistant-context.ts";
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

export default function QuestionBankPage() {
  const [profileId, setProfileId] = useState("");
  const [banks, setBanks] = useState<QuestionBank[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [filter, setFilter] = useState<CategoryFilter>("ALL");
  const [bankName, setBankName] = useState("我的题库");
  const [newQuestion, setNewQuestion] = useState("");
  const [newCategory, setNewCategory] = useState<QuestionCategory>("BASIC");
  const [newDifficulty, setNewDifficulty] = useState<QuestionDifficulty>("MEDIUM");
  const [newStyle, setNewStyle] = useState("");
  const [asReal, setAsReal] = useState(false);
  const [suggestions, setSuggestions] = useState<Record<string, ResumeSuggestion[]>>({});

  const load = useCallback(async () => {
    const pid = readCurrentProfileId();
    setProfileId(pid);
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

  useEffect(() => {
    void load();
  }, [load]);

  const items = useMemo(() => {
    const all = banks.flatMap((bank) => bank.items);
    const filtered = filter === "ALL" ? all : all.filter((item) => item.category === filter);
    return filtered;
  }, [banks, filter]);

  const activeBankId = banks[0]?.id ?? "";

  const handleCreateBank = useCallback(async () => {
    if (!profileId || !bankName.trim()) return;
    setBusyId("new-bank");
    try {
      await createQuestionBank(profileId, bankName.trim());
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "创建题库失败。");
    } finally {
      setBusyId("");
    }
  }, [bankName, load, profileId]);

  // 第六阶段：按当前岗位/岗位版简历的真实上下文生成三分类题库。
  const handleGenerateFromContext = useCallback(async () => {
    if (!profileId) return;
    setBusyId("generate");
    try {
      const context = readAssistantContext();
      await generateQuestionBank(profileId, {
        mission_id: context.missionId,
        target_resume_id: context.targetResumeId,
      });
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "按岗位生成题库失败。");
    } finally {
      setBusyId("");
    }
  }, [load, profileId]);

  const handleAddQuestion = useCallback(async () => {
    if (!profileId || !newQuestion.trim()) return;
    setBusyId("new-question");
    try {
      const payload = {
        question_text: newQuestion.trim(),
        category: newCategory,
        difficulty: newDifficulty,
        interviewer_style: newStyle.trim() || undefined,
      };
      if (asReal) {
        await createRealQuestion(profileId, payload);
      } else {
        let bankId = activeBankId;
        if (!bankId) {
          const bank = await createQuestionBank(profileId, "我的题库");
          bankId = bank.id;
        }
        await addQuestionItem(bankId, { ...payload, source: "MODEL" });
      }
      setNewQuestion("");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "添加题目失败。");
    } finally {
      setBusyId("");
    }
  }, [activeBankId, asReal, load, newCategory, newDifficulty, newQuestion, newStyle, profileId]);

  const handleReferenceAnswer = useCallback(
    async (item: QuestionItem) => {
      setBusyId(item.id);
      try {
        await generateReferenceAnswer(item.id);
        await load();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "生成参考答案失败。");
      } finally {
        setBusyId("");
      }
    },
    [load],
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
          <p className="app-eyebrow">Question Bank</p>
          <h1 className="app-page-title">题库</h1>
          <p className="app-page-subtitle">基础题 / 项目深挖 / HR 面三类问题独立沉淀，可练单题参考答案，也可录入真实面经题目。</p>
        </div>
      </header>

      {error && <p className="app-inline-error" role="alert">{error}</p>}

      {!profileId && !loading ? (
        <section className="app-card app-empty">还没有简历档案，请先上传简历后再建题库。</section>
      ) : (
        <>
          <section className="app-card" aria-label="新建题目">
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
                按当前岗位生成题库
              </button>
            </div>
          </section>

          <section className="app-card" aria-label="题目列表">
            <div className="question-card-head">
              <strong>题目（{items.length}）</strong>
              <div className="question-meta">
                {(["ALL", ...QUESTION_CATEGORIES] as CategoryFilter[]).map((value) => (
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
              <p className="app-muted">还没有题目，先在上方添加一道。</p>
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
      )}
    </main>
  );
}
