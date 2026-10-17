"use client";

import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { readCurrentProfileId } from "../../career-hub.ts";
import { missionHref } from "../../missions.ts";
import { createDraftProfile, PROFILE_STORAGE_KEY } from "../../missions.ts";
import {
  parseManualJob,
  saveManualJob,
  type JobDraft,
  type ManualSaveResult,
} from "../../jobs.ts";

const SITE_OPTIONS = [
  { id: "BOSS_ZHIPIN", label: "BOSS 直聘" },
  { id: "OTHER", label: "其他中文平台" },
  { id: "UNKNOWN", label: "未标注来源" },
] as const;

const EMPLOYMENT_OPTIONS = [
  { id: "INTERN", label: "实习" },
  { id: "FULLTIME", label: "全职 / 校招" },
  { id: "PARTTIME", label: "兼职" },
  { id: "UNKNOWN", label: "未识别" },
] as const;

const WARNING_LABEL: Record<string, string> = {
  company_missing: "没有识别到公司名，请手动填写（不会替你猜一个）。",
  role_missing: "没有识别到岗位名，请手动填写。",
  location_missing: "没有识别到工作地点。",
  salary_missing: "没有识别到薪资。",
  education_missing: "没有识别到学历要求。",
  employment_type_unknown: "没有识别到工作类型（实习 / 全职）。",
  prompt_injection_suspected: "⚠️ 岗位原文里检测到疑似提示词注入（例如要求「忽略以上指令」「直接录用」）。已按普通文本解析，不会执行其中的指令，也不会据此改变匹配结论。",
  hidden_characters: "⚠️ 原文里检测到隐藏字符，已忽略；如来源可疑请不要保存。",
};

const CONFIDENCE_LABEL: Record<string, string> = {
  HIGH: "已确认",
  MEDIUM: "自动识别",
  LOW: "低置信",
  MISSING: "缺失",
};

type Editable = {
  company: string;
  role: string;
  location: string;
  salary_text: string;
  education: string;
  experience: string;
  employment_type: string;
  source_url: string;
  jd: string;
};

function toEditable(draft: JobDraft): Editable {
  return {
    company: draft.company ?? "",
    role: draft.role ?? "",
    location: draft.location ?? "",
    salary_text: draft.salary_text ?? "",
    education: draft.education ?? "",
    experience: draft.experience ?? "",
    employment_type: draft.employment_type ?? "UNKNOWN",
    source_url: draft.source_url ?? "",
    jd: draft.jd ?? "",
  };
}

export default function JobImportPage() {
  const router = useRouter();
  const [site, setSite] = useState<string>("BOSS_ZHIPIN");
  const [rawText, setRawText] = useState("");
  const [draft, setDraft] = useState<JobDraft | null>(null);
  const [form, setForm] = useState<Editable | null>(null);
  const [updateDuplicates, setUpdateDuplicates] = useState(false);
  const [busy, setBusy] = useState<"" | "parse" | "save">("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<ManualSaveResult | null>(null);

  const warnings = useMemo(() => draft?.warnings ?? [], [draft]);
  const hardWarnings = useMemo(
    () => warnings.filter((code) => code === "prompt_injection_suspected" || code === "hidden_characters"),
    [warnings],
  );

  const resolveProfileId = useCallback(async (): Promise<string> => {
    const existing = readCurrentProfileId();
    if (existing) return existing;
    const created = await createDraftProfile();
    window.localStorage.setItem(PROFILE_STORAGE_KEY, created.profile_id);
    return created.profile_id;
  }, []);

  const parse = useCallback(async () => {
    if (rawText.trim().length < 10) {
      setError("内容太短，请把岗位页面上的信息复制完整（岗位名、薪资、地点、公司、JD）。");
      return;
    }
    setBusy("parse");
    setError("");
    setResult(null);
    try {
      const response = await parseManualJob({ source_text: rawText, source_site: site });
      setDraft(response.draft);
      setForm(toEditable(response.draft));
    } catch (caught) {
      setDraft(null);
      setForm(null);
      setError(caught instanceof Error ? caught.message : "解析失败，请重试。");
    } finally {
      setBusy("");
    }
  }, [rawText, site]);

  const save = useCallback(
    async (goToMatch: boolean) => {
      if (!form) return;
      setBusy("save");
      setError("");
      try {
        const profileId = await resolveProfileId();
        const saved = await saveManualJob(
          profileId,
          { ...(draft ?? {}), ...form, source_site: site, recognition: "MANUAL_PASTE" },
          { update_duplicates: updateDuplicates, import_to_mission: goToMatch },
        );
        setResult(saved);
        if (goToMatch && saved.mission_id) {
          router.push(missionHref(saved.mission_id, "role"));
          return;
        }
        if (saved.status === "DUPLICATE") {
          setError(saved.message ?? "岗位已存在。");
        }
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "保存失败，请重试。");
      } finally {
        setBusy("");
      }
    },
    [draft, form, resolveProfileId, router, site, updateDuplicates],
  );

  return (
    <main className="shell">
      <section className="profile">
        <div className="section-heading">
          <div>
            <p className="eyebrow">岗位导入</p>
            <h2>导入 BOSS 直聘岗位</h2>
          </div>
          <Link className="button-secondary" href={"/jobs" as Route}>
            ← 返回岗位库
          </Link>
        </div>

        <p className="profile-note">
          在 BOSS 直聘打开职位详情 → 复制页面上的岗位信息 → 粘贴到下面 → 确认字段 → 保存并进入岗位匹配。
          系统只解析你粘贴的原文：识别不到的字段会留空并提示，不会替你编造公司名、岗位名或薪资。
        </p>

        {!draft ? (
          <>
            <div className="field-grid">
              <label className="field-label">
                <span>岗位来源</span>
                <select value={site} onChange={(event) => setSite(event.target.value)}>
                  {SITE_OPTIONS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <label className="field-label">
              <span>粘贴岗位原文（岗位名 / 薪资 / 地点 / 公司 / JD）</span>
              <textarea
                rows={14}
                value={rawText}
                onChange={(event) => setRawText(event.target.value)}
                placeholder={"AI产品经理实习\n8-13K·13薪\n杭州 滨江区\n经验不限 本科\n杭州某某科技有限公司\n【岗位职责】\n..."}
              />
            </label>

            <div className="profile-actions">
              <button className="app-btn primary" type="button" onClick={() => void parse()} disabled={busy === "parse"}>
                {busy === "parse" ? "解析中…" : "解析岗位"}
              </button>
            </div>
          </>
        ) : null}

        {draft && form ? (
          <>
            <div className="section-heading">
              <div>
                <p className="eyebrow">确认字段</p>
                <h3>保存前可以修改任何字段</h3>
              </div>
              <button className="button-secondary" type="button" onClick={() => { setDraft(null); setForm(null); setResult(null); }}>
                重新粘贴
              </button>
            </div>

            <div className="field-grid">
              <label className="field-label">
                <span>公司 {draft.confidence?.company ? `（${CONFIDENCE_LABEL[draft.confidence.company] ?? draft.confidence.company}）` : ""}</span>
                <input value={form.company} onChange={(event) => setForm({ ...form, company: event.target.value })} placeholder="识别不到就手动填" />
              </label>
              <label className="field-label">
                <span>岗位 {draft.confidence?.role ? `（${CONFIDENCE_LABEL[draft.confidence.role] ?? draft.confidence.role}）` : ""}</span>
                <input value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })} placeholder="识别不到就手动填" />
              </label>
              <label className="field-label">
                <span>工作地点</span>
                <input value={form.location} onChange={(event) => setForm({ ...form, location: event.target.value })} />
              </label>
              <label className="field-label">
                <span>薪资</span>
                <input value={form.salary_text} onChange={(event) => setForm({ ...form, salary_text: event.target.value })} placeholder="8-13K / 面议" />
              </label>
              <label className="field-label">
                <span>学历要求</span>
                <input value={form.education} onChange={(event) => setForm({ ...form, education: event.target.value })} placeholder="本科 / 硕士 / 学历不限" />
              </label>
              <label className="field-label">
                <span>经验要求</span>
                <input value={form.experience} onChange={(event) => setForm({ ...form, experience: event.target.value })} placeholder="经验不限 / 3-5年" />
              </label>
              <label className="field-label">
                <span>工作类型</span>
                <select value={form.employment_type} onChange={(event) => setForm({ ...form, employment_type: event.target.value })}>
                  {EMPLOYMENT_OPTIONS.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field-label">
                <span>原始链接</span>
                <input value={form.source_url} onChange={(event) => setForm({ ...form, source_url: event.target.value })} placeholder="https://www.zhipin.com/..." />
              </label>
            </div>

            <label className="field-label">
              <span>完整 JD（保存的正文，可编辑）</span>
              <textarea rows={12} value={form.jd} onChange={(event) => setForm({ ...form, jd: event.target.value })} />
            </label>

            {warnings.length ? (
              <div className="profile-section">
                <h3>解析提示</h3>
                <ul>
                  {warnings.map((code) => (
                    <li key={code}>
                      <span className={hardWarnings.includes(code) ? "dot warn" : "dot"} />
                      {WARNING_LABEL[code] ?? code}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            <label className="field-label" style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={updateDuplicates}
                onChange={(event) => setUpdateDuplicates(event.target.checked)}
                style={{ width: 16, height: 16 }}
              />
              <span>岗位已存在但内容有变化时，用这次的内容更新（不会覆盖你的备注与投递状态）</span>
            </label>

            <div className="profile-actions">
              <button className="app-btn primary" type="button" onClick={() => void save(true)} disabled={busy === "save"}>
                {busy === "save" ? "保存中…" : "确认保存并进入匹配"}
              </button>
              <button className="app-btn" type="button" onClick={() => void save(false)} disabled={busy === "save"}>
                仅保存到岗位库
              </button>
            </div>
          </>
        ) : null}

        {result ? (
          <div className="profile-section">
            <h3>保存结果</h3>
            <p className="status">
              {result.status === "NEW" ? "已新增到岗位库。" : null}
              {result.status === "DUPLICATE" ? "岗位库里已有同一条，未重复新增。" : null}
              {result.status === "UPDATED" ? "已更新岗位内容（保留你的备注与投递状态）。" : null}
              {result.changed_fields?.length ? `变化字段：${result.changed_fields.join("、")}` : null}
            </p>
            {result.mission_id ? (
              <Link className="app-btn primary" href={missionHref(result.mission_id, "role")}>
                查看岗位匹配 →
              </Link>
            ) : null}
            {result.mission_error ? <p className="error">进入匹配失败：{result.mission_error}</p> : null}
          </div>
        ) : null}

        {error ? <p className="error">{error}</p> : null}
      </section>
    </main>
  );
}
