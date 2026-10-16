"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { readCurrentProfileId } from "../career-hub.ts";
import { missionHref } from "../missions.ts";
import {
  cancelCollectRun,
  collectBrowserPage,
  collectJobs,
  extractJobFile,
  fetchJobUrl,
  healthCheckSource,
  importCandidateJob,
  parseCandidateJobs,
  readBridgeStatus,
  readCollectRun,
  readJobLibrary,
  readJobSources,
  saveCollectedJobs,
  startCollectRun,
  type BridgeStatus,
  type BrowserCapture,
  type CollectedJob,
  type CollectFilter,
  type CollectResult,
  type CollectResultStatus,
  type CollectTaskSnapshot,
  type CollectTaskStatus,
  type JobSource,
  type LibraryItem,
} from "../jobs.ts";

type IntakeMode = "paste" | "url" | "file";

const MODE_LABEL: Record<IntakeMode, string> = {
  paste: "粘贴完整 JD",
  url: "公开招聘链接",
  file: "岗位截图 / PDF / 文档",
};

const KEYWORD_PRESETS = ["AI 产品经理", "Agent 产品经理", "AI PM 实习", "product manager", "intern"];

const SOURCE_LABELS: Record<string, string> = {
  remoteok: "RemoteOK",
  remotive: "Remotive",
  greenhouse: "Greenhouse",
  lever: "Lever",
  browser: "当前网页",
  paste: "粘贴",
  file: "文件",
};

const EMPLOYMENT_LABEL: Record<string, string> = {
  INTERN: "实习",
  FULLTIME: "全职",
  UNKNOWN: "未标注",
};

const CONFIRM_LABEL: Record<string, string> = {
  company: "企业",
  role: "岗位",
  location: "地点",
  jd: "JD",
};

const POSTED_OPTIONS: Array<{ value: number; label: string }> = [
  { value: 0, label: "不限时间" },
  { value: 7, label: "7 天内" },
  { value: 30, label: "30 天内" },
  { value: 90, label: "90 天内" },
];

const RESULT_STATUS_LABEL: Record<CollectResultStatus, { label: string; tone: string; hint: string }> = {
  NEW: { label: "新增", tone: "filled", hint: "岗位库里还没有这条，可以直接保存。" },
  DUPLICATE: { label: "已存在", tone: "muted", hint: "库里已有同一岗位且正文一致，保存会自动跳过。" },
  UPDATED: { label: "有更新", tone: "warn", hint: "库里已有同一岗位，但 JD 正文变化了，可勾选「同时更新已有岗位」覆盖。" },
  NEEDS_REVIEW: { label: "待确认", tone: "warn", hint: "关键字段缺失或置信度低，保存后需要补齐才能进入 JD 分析。" },
  FAILED: { label: "不可用", tone: "danger", hint: "结构化字段不足，无法入库。" },
};

const TASK_STATUS_LABEL: Record<CollectTaskStatus, string> = {
  IDLE: "待开始",
  RUNNING: "采集中",
  COMPLETED: "采集完成",
  PARTIAL: "部分来源失败",
  FAILED: "采集失败",
  CANCELLED: "已取消",
};

const SOURCE_STATUS_LABEL: Record<string, string> = {
  OK: "成功",
  EMPTY: "无命中",
  ERROR: "失败",
  TIMEOUT: "超时",
  CANCELLED: "已取消",
};

function jobKey(job: CollectedJob): string {
  return job.dedupe_key || `${job.source}|${job.source_url}|${job.company}|${job.role}`;
}

function formatTime(value?: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString("zh-CN");
}

export default function JobsPage() {
  const router = useRouter();
  const [profileId, setProfileId] = useState("");
  const [sources, setSources] = useState<JobSource[]>([]);

  // ---- 一键采集
  const [keywordDraft, setKeywordDraft] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [city, setCity] = useState("");
  const [employment, setEmployment] = useState("ANY");
  const [pickedSources, setPickedSources] = useState<string[]>(["remoteok"]);
  const [postedDays, setPostedDays] = useState(0);
  const [limit, setLimit] = useState(20);
  const [collectTimeout, setCollectTimeout] = useState(90);
  const [boards, setBoards] = useState("");
  const [leverSlugs, setLeverSlugs] = useState("");
  const [collecting, setCollecting] = useState(false);
  const [task, setTask] = useState<CollectTaskSnapshot | null>(null);
  const [collectProgress, setCollectProgress] = useState<string[]>([]);
  const [collectResult, setCollectResult] = useState<CollectResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [rowBusy, setRowBusy] = useState("");
  const [updateDuplicates, setUpdateDuplicates] = useState(false);
  const [health, setHealth] = useState<Record<string, { status: string; note: string; latency_ms?: number }>>({});
  const [healthBusy, setHealthBusy] = useState("");

  // ---- 浏览器采集
  const [bridge, setBridge] = useState<BridgeStatus | null>(null);
  const [capture, setCapture] = useState<BrowserCapture | null>(null);
  const [captureBusy, setCaptureBusy] = useState(false);
  const [captureDraft, setCaptureDraft] = useState<{ company: string; role: string; location: string; jd: string } | null>(null);

  // ---- 手动导入
  const [mode, setMode] = useState<IntakeMode>("paste");
  const [pasteText, setPasteText] = useState("");
  const [url, setUrl] = useState("");

  // ---- 岗位库
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [facets, setFacets] = useState<{ companies: string[]; locations: string[] }>({ companies: [], locations: [] });
  const [keyword, setKeyword] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [kind, setKind] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const refreshLibrary = useCallback(
    async (pid: string, filters: { q?: string; company?: string; location?: string; kind?: string }) => {
      if (!pid) return;
      try {
        const result = await readJobLibrary(pid, filters);
        setLibrary(result.items);
        setFacets(result.facets);
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "读取岗位库失败。");
      }
    },
    [],
  );

  useEffect(() => {
    const pid = readCurrentProfileId();
    setProfileId(pid);
    void readJobSources()
      .then((result) => setSources(result.sources))
      .catch(() => setSources([]));
    void readBridgeStatus()
      .then(setBridge)
      .catch(() => setBridge({ available: false, bridge_url: "", error: "无法读取浏览器桥状态" }));
    void refreshLibrary(pid, {});
  }, [refreshLibrary]);

  const applyFilters = useCallback(
    (override?: { keyword?: string; company?: string; location?: string; kind?: string }) => {
      void refreshLibrary(profileId, {
        q: override?.keyword ?? keyword,
        company: override?.company ?? company,
        location: override?.location ?? location,
        kind: override?.kind ?? kind,
      });
    },
    [company, keyword, kind, location, profileId, refreshLibrary],
  );

  const requireProfile = (): boolean => {
    if (!profileId) {
      setError("还没有简历档案，请先到「简历」上传简历。");
      return false;
    }
    return true;
  };

  // ---------------------------------------------------------------- 一键采集

  const addKeyword = useCallback((value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return;
    setKeywords((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]));
  }, []);

  const buildCollectPayload = useCallback(
    (): CollectFilter => ({
      keywords,
      sources: pickedSources,
      location: city.trim() || undefined,
      employment_type: employment === "ANY" ? undefined : employment,
      posted_within_days: postedDays || undefined,
      limit,
      greenhouse_boards: boards
        .split(/[,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
      lever_companies: leverSlugs
        .split(/[,，\s]+/)
        .map((item) => item.trim())
        .filter(Boolean),
      timeout_seconds: collectTimeout || null,
    }),
    [boards, city, collectTimeout, employment, keywords, leverSlugs, limit, pickedSources, postedDays],
  );

  const summarizeResult = useCallback((result: CollectResult, logs: string[]) => {
    setCollectProgress(
      logs.length
        ? logs
        : result.reports.map(
            (report) =>
              `${SOURCE_LABELS[report.source] ?? report.source}：${SOURCE_STATUS_LABEL[report.status] ?? report.status}` +
              `（抓到 ${report.fetched ?? report.count} 条 → 筛选后 ${report.count} 条` +
              `${report.filtered_out ? `，本地排除 ${report.filtered_out} 条` : ""}` +
              `${report.latency_ms !== undefined ? `，耗时 ${report.latency_ms}ms` : ""}` +
              `${report.note ? `，${report.note}` : ""}）`,
          ),
    );
    const failed = result.reports.filter((item) => item.status === "ERROR" || item.status === "TIMEOUT");
    if (!result.jobs.length && failed.length) {
      setError(`采集失败：${failed.map((item) => `${item.source} — ${item.note}`).join("；")}`);
    } else if (!result.jobs.length) {
      setInfo("采集完成，但没有岗位命中当前筛选条件。可以放宽关键词或时间范围再试。");
    }
  }, []);

  const handleCollect = useCallback(async () => {
    setError("");
    setInfo("");
    if (!pickedSources.length) {
      setError("请至少选择一个采集来源。");
      return;
    }
    setCollecting(true);
    setCollectProgress([]);
    setCollectResult(null);
    setTask(null);
    setSelected(new Set());
    setHealth({});
    const payload = buildCollectPayload();

    // 没有档案时无法与岗位库比对，退回到不带结果状态的同步接口，但结果一样是真实采集。
    if (!profileId) {
      try {
        const result = await collectJobs(payload);
        setCollectResult(result);
        setSelected(new Set(result.jobs.map(jobKey)));
        summarizeResult(result, []);
        setInfo("未选择简历档案，结果未与岗位库比对（不会显示新增/已存在）。");
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "采集失败。");
      } finally {
        setCollecting(false);
      }
      return;
    }

    try {
      const snapshot = await startCollectRun(profileId, payload);
      setTask(snapshot);
      let current = snapshot;
      const deadline = Date.now() + 180_000;
      while (current.status === "RUNNING" && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, 700));
        current = await readCollectRun(snapshot.task_id);
        setTask(current);
      }
      if (current.status === "RUNNING") {
        await cancelCollectRun(snapshot.task_id).catch(() => undefined);
        setError("采集超过 3 分钟仍未结束，已自动取消。请减少来源或缩小条数后重试。");
      }
      if (current.result) {
        setCollectResult(current.result);
        setSelected(
          new Set(
            current.result.jobs
              .filter((job) => job.result_status !== "DUPLICATE" && job.result_status !== "FAILED")
              .map(jobKey),
          ),
        );
        const logs = current.progress
          .filter((event) => event.type === "SOURCE_FINISHED")
          .map((event) => `${event.source}：已完成（抓到 ${event.fetched} 条，保留 ${event.kept} 条）`);
        summarizeResult(current.result, logs);
      }
      if (current.error) setError(current.error);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "采集失败。");
    } finally {
      setCollecting(false);
    }
  }, [buildCollectPayload, pickedSources, profileId, summarizeResult]);

  const handleCancelCollect = useCallback(async () => {
    if (!task) return;
    try {
      await cancelCollectRun(task.task_id);
      setInfo("已请求取消，任务会在当前来源结束后停止。");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "取消失败。");
    }
  }, [task]);

  const runHealthCheck = useCallback(
    async (sourceId: string) => {
      setHealthBusy(sourceId);
      setError("");
      try {
        const report = await healthCheckSource(sourceId, {
          greenhouse_boards: boards.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean),
          lever_companies: leverSlugs.split(/[,，\s]+/).map((item) => item.trim()).filter(Boolean),
        });
        setHealth((prev) => ({ ...prev, [sourceId]: { status: report.status, note: report.note, latency_ms: report.latency_ms } }));
      } catch (caught) {
        setHealth((prev) => ({
          ...prev,
          [sourceId]: { status: "ERROR", note: caught instanceof Error ? caught.message : "自检失败" },
        }));
      } finally {
        setHealthBusy("");
      }
    },
    [boards, leverSlugs],
  );

  const handleSaveSelected = useCallback(async () => {
    if (!requireProfile() || !collectResult) return;
    const jobs = collectResult.jobs.filter((job) => selected.has(jobKey(job)));
    if (!jobs.length) {
      setError("没有勾选任何采集结果。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const result = await saveCollectedJobs(profileId, jobs, updateDuplicates);
      const parts = [`新增保存 ${result.saved_count} 条`, `跳过 ${result.skipped_count} 条`];
      if (result.updated_count) parts.push(`更新已有岗位 ${result.updated_count} 条`);
      setInfo(`${parts.join("，")}。${result.skipped_count ? "（已存在且正文一致的岗位不会重复入库）" : ""}`);
      applyFilters();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败。");
    } finally {
      setSaving(false);
    }
  }, [applyFilters, collectResult, profileId, selected, updateDuplicates]);

  /** 保存 → 导入正式岗位 → 跳到对应 Mission 页签。 */
  const openMissionFor = useCallback(
    async (job: CollectedJob | null, candidateId: string | null, tab: "role" | "resume", label: string) => {
      if (!requireProfile()) return;
      const marker = `${label}:${job ? jobKey(job) : candidateId ?? ""}`;
      setRowBusy(marker);
      setError("");
      try {
        let id = candidateId;
        if (!id) {
          if (!job) throw new Error("没有可导入的岗位。");
          const saved = await saveCollectedJobs(profileId, [job]);
          if (!saved.saved_count) {
            // 已经在库里：直接复用已有候选草稿，不要让用户再困惑地重找一遍。
            const skipped = saved.skipped[0] as { reason?: string; matches?: Array<{ kind: string; id: string }> } | undefined;
            const existing = skipped?.matches?.find((item) => item.kind === "CANDIDATE");
            if (!existing) {
              throw new Error(
                skipped?.reason === "DUPLICATE" ? "这个岗位已经在岗位库里了，但没找到可复用的草稿，请到下方岗位库刷新后打开。" : "保存失败，未返回候选岗位。",
              );
            }
            id = existing.id;
          } else {
            id = saved.saved[0].candidate_ids[0];
          }
        }
        const imported = await importCandidateJob(id);
        applyFilters();
        router.push(missionHref(imported.mission_id, tab));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "打开岗位工作台失败。");
      } finally {
        setRowBusy("");
      }
    },
    [applyFilters, profileId, router],
  );

  // ---------------------------------------------------------------- 采集当前网页

  const handleCapture = useCallback(async () => {
    setCaptureBusy(true);
    setError("");
    setCapture(null);
    setCaptureDraft(null);
    try {
      const result = await collectBrowserPage();
      setCapture(result);
      if (result.job) {
        setCaptureDraft({
          company: result.job.company || "",
          role: result.job.role || "",
          location: result.job.location || "",
          jd: result.job.jd || "",
        });
      }
      if (result.status !== "OK") {
        setInfo("");
        setError(result.note || `无法读取当前页面（状态：${result.status}）`);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "采集当前网页失败。");
    } finally {
      setCaptureBusy(false);
    }
  }, []);

  const handleSaveCapture = useCallback(async () => {
    if (!requireProfile() || !capture?.job || !captureDraft) return;
    if (!captureDraft.role.trim() || !captureDraft.jd.trim()) {
      setError("岗位名称和 JD 不能为空，请先补齐再保存。");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const job: CollectedJob = {
        ...capture.job,
        company: captureDraft.company.trim(),
        role: captureDraft.role.trim(),
        location: captureDraft.location.trim(),
        jd: captureDraft.jd.trim(),
        needs_confirm: [],
        text: `公司：${captureDraft.company}\n职位：${captureDraft.role}\n地点：${captureDraft.location}\n\n${captureDraft.jd}`,
      };
      const result = await saveCollectedJobs(profileId, [job]);
      if (!result.saved_count) {
        const reason = (result.skipped[0] as { reason?: string } | undefined)?.reason;
        setError(reason === "DUPLICATE" ? "这个岗位已经在岗位库里了。" : "保存失败。");
        return;
      }
      setInfo("已保存到岗位库，可在下方岗位库继续操作。");
      setCapture(null);
      setCaptureDraft(null);
      applyFilters();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败。");
    } finally {
      setSaving(false);
    }
  }, [applyFilters, capture, captureDraft, profileId]);

  // ---------------------------------------------------------------- 手动导入

  const handlePaste = useCallback(async () => {
    if (!requireProfile()) return;
    if (pasteText.trim().length < 20) {
      setError("请粘贴完整的岗位描述（至少 20 个字符）。");
      return;
    }
    setBusy("paste");
    setError("");
    try {
      const rows = await parseCandidateJobs(profileId, pasteText, "PASTE");
      setInfo(`已解析出 ${rows.length} 条岗位草稿，已进入岗位库。`);
      setPasteText("");
      applyFilters();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "解析岗位失败。");
    } finally {
      setBusy("");
    }
  }, [applyFilters, pasteText, profileId]);

  const handleUrl = useCallback(async () => {
    if (!requireProfile()) return;
    setBusy("url");
    setError("");
    try {
      const fetched = await fetchJobUrl(url);
      if (fetched.status !== "PARSED") {
        setInfo("");
        setError(`${fetched.note}（状态：${fetched.status}）`);
        return;
      }
      const rows = await parseCandidateJobs(profileId, fetched.text, "LINK");
      setInfo(`已从公开页面采集并解析出 ${rows.length} 条岗位草稿（标题：${fetched.title || "无"}）。`);
      setUrl("");
      applyFilters();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "采集链接失败。");
    } finally {
      setBusy("");
    }
  }, [applyFilters, profileId, url]);

  const handleFile = useCallback(
    async (file: File) => {
      if (!requireProfile()) return;
      setBusy("file");
      setError("");
      try {
        const extracted = await extractJobFile(file);
        if (extracted.status !== "PARSED") {
          setError(`${extracted.note}（状态：${extracted.status}）`);
          return;
        }
        const sourceKind = file.name.toLowerCase().endsWith(".pdf") ? "FILE_PDF" : "FILE_TXT";
        const rows = await parseCandidateJobs(profileId, extracted.text, sourceKind);
        setInfo(`已从 ${file.name} 解析出 ${rows.length} 条岗位草稿。`);
        applyFilters();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "解析文件失败。");
      } finally {
        setBusy("");
      }
    },
    [applyFilters, profileId],
  );

  const handleImport = useCallback(
    async (item: LibraryItem) => {
      setBusy(`import:${item.id}`);
      setError("");
      try {
        const result = await importCandidateJob(item.id);
        setInfo(`已导入为正式岗位：${result.company} · ${result.role}。`);
        applyFilters();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "导入岗位失败。");
      } finally {
        setBusy("");
      }
    },
    [applyFilters],
  );

  // 只有真正的采集适配器能进「来源」选择；generic_url / file 属于手动导入区。
  const adapterSources = useMemo(() => sources.filter((item) => item.mode === "adapter"), [sources]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Job Intake</p>
          <h1 className="app-page-title">岗位广场</h1>
          <p className="app-page-subtitle">
            一键采集真实在招岗位、采集当前招聘网页，或手动导入。保存进岗位库后可直接：JD 分析 → 经历四分类 → 定向简历 → Resume Studio → PDF。
          </p>
        </div>
      </header>

      {error && (
        <p className="app-inline-error" role="alert">
          {error}
        </p>
      )}
      {info && <p className="app-muted">{info}</p>}

      {/* ---------------------------------------------------------------- 一键采集 */}
      <section className="app-card" aria-label="一键采集岗位">
        <h2 className="app-card-title">1 · 一键采集岗位</h2>

        <div className="app-field-block">
          <label className="app-field-label">关键词（可多个，任一命中即算）</label>
          <div className="app-row">
            <input
              value={keywordDraft}
              onChange={(event) => setKeywordDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === "," || event.key === "，") {
                  event.preventDefault();
                  addKeyword(keywordDraft);
                  setKeywordDraft("");
                }
              }}
              placeholder="输入后回车添加，例如：AI 产品经理"
            />
            <button
              type="button"
              className="app-btn"
              onClick={() => {
                addKeyword(keywordDraft);
                setKeywordDraft("");
              }}
            >
              添加
            </button>
          </div>
          {keywords.length > 0 ? (
            <div className="app-chip-row">
              {keywords.map((item) => (
                <span className="app-chip" key={item}>
                  {item}
                  <button
                    type="button"
                    aria-label={`移除 ${item}`}
                    onClick={() => setKeywords((prev) => prev.filter((value) => value !== item))}
                  >
                    ×
                  </button>
                </span>
              ))}
              <button type="button" className="app-btn subtle" onClick={() => setKeywords([])}>
                清空
              </button>
            </div>
          ) : (
            <div className="app-chip-row">
              {KEYWORD_PRESETS.map((item) => (
                <button type="button" key={item} className="app-chip ghost" onClick={() => addKeyword(item)}>
                  + {item}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="app-filter-row">
          <input value={city} onChange={(event) => setCity(event.target.value)} placeholder="城市（可选，如 北京 / Remote）" />
          <select value={employment} onChange={(event) => setEmployment(event.target.value)}>
            <option value="ANY">实习 / 全职不限</option>
            <option value="INTERN">只要实习</option>
            <option value="FULLTIME">只要全职</option>
          </select>
          <select value={postedDays} onChange={(event) => setPostedDays(Number(event.target.value))}>
            {POSTED_OPTIONS.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={1}
            max={50}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value) || 20)}
            style={{ maxWidth: "7rem" }}
            aria-label="最多返回条数"
          />
          <input
            type="number"
            min={10}
            max={300}
            value={collectTimeout}
            onChange={(event) => setCollectTimeout(Number(event.target.value) || 90)}
            style={{ maxWidth: "8rem" }}
            aria-label="整轮采集时间上限（秒）"
            title="达到上限后，剩余来源不再请求，任务标记为 PARTIAL"
          />
        </div>
        <p className="app-card-meta">
          城市 / 实习 / 发布时间属于**采集后本地过滤**：目前所有公开来源都不支持按这些条件在服务端检索，
          所以「抓到 N 条」不等于「符合筛选条件 N 条」，下方统计条会把两者分开显示。
        </p>

        <div className="app-field-block">
          <label className="app-field-label">采集来源</label>
          <div className="app-chip-row">
          {adapterSources.map((item) => (
            <span className="app-chip-row" key={item.id} style={{ gap: "0.35rem" }}>
              <button
                type="button"
                className={`app-chip${pickedSources.includes(item.id) ? " active" : ""}`}
                onClick={() =>
                  setPickedSources((prev) =>
                    prev.includes(item.id) ? prev.filter((value) => value !== item.id) : [...prev, item.id],
                  )
                }
                title={item.note}
              >
                {item.label}
                {item.filter_mode === "local" ? <em className="app-chip-note">本地过滤</em> : null}
              </button>
              {item.has_collect ? (
                <button
                  type="button"
                  className="app-btn subtle"
                  disabled={healthBusy === item.id}
                  onClick={() => void runHealthCheck(item.id)}
                  title="真实请求一次该来源的健康检查接口"
                >
                  {healthBusy === item.id ? "自检中…" : "自检"}
                </button>
              ) : null}
            </span>
          ))}
          {Object.entries(health).map(([sourceId, report]) => (
            <p className="app-card-meta" key={`health-${sourceId}`}>
              自检结果 · {SOURCE_LABELS[sourceId] ?? sourceId}：
              <strong>{report.status}</strong>
              {report.latency_ms !== undefined ? `（${report.latency_ms}ms）` : ""}
              {report.note ? ` — ${report.note}` : ""}
            </p>
          ))}
          {adapterSources.filter((item) => item.presets?.length).map((item) => (
            <div className="app-chip-row" key={`presets-${item.id}`}>
              <span className="app-muted">{item.label} 已验证标识（点击填入）：</span>
              {item.presets?.map((preset) => (
                <button
                  type="button"
                  key={preset}
                  className="app-chip ghost"
                  onClick={() => {
                    const value = item.config_key === "lever_companies" ? leverSlugs : boards;
                    const next = value
                      .split(/[,，\s]+/)
                      .map((entry) => entry.trim())
                      .filter(Boolean);
                    if (!next.includes(preset)) next.push(preset);
                    if (item.config_key === "lever_companies") setLeverSlugs(next.join(","));
                    else setBoards(next.join(","));
                  }}
                >
                  + {preset}
                </button>
              ))}
            </div>
          ))}
          </div>
          {pickedSources.includes("greenhouse") ? (
            <div className="app-row">
              <input
                value={boards}
                onChange={(event) => setBoards(event.target.value)}
                placeholder="Greenhouse 招聘板标识，逗号分隔：stripe,airbnb,databricks"
                style={{ flex: 1 }}
              />
            </div>
          ) : null}
          {pickedSources.includes("lever") ? (
            <div className="app-row">
              <input
                value={leverSlugs}
                onChange={(event) => setLeverSlugs(event.target.value)}
                placeholder="Lever 企业标识，逗号分隔：leverdemo"
                style={{ flex: 1 }}
              />
            </div>
          ) : null}
          <p className="app-card-meta">
            Greenhouse / Lever 是**按企业招聘板**配置的公开接口，不是全网检索：需要填写对应企业的招聘板标识，填错会返回真实错误（如 HTTP 404），系统不会用演示数据顶替。
          </p>
        </div>

        <div className="app-row">
          <button type="button" className="app-btn primary" disabled={collecting} onClick={() => void handleCollect()}>
            {collecting ? "采集中…" : "开始采集"}
          </button>
          <button
            type="button"
            className="app-btn"
            disabled={!collecting || !task}
            onClick={() => void handleCancelCollect()}
          >
            取消采集
          </button>
          {task ? (
            <span className={`app-badge${task.status === "FAILED" ? " warn" : task.status === "CANCELLED" ? " warn" : " filled"}`}>
              任务状态：{TASK_STATUS_LABEL[task.status] ?? task.status}
            </span>
          ) : null}
          {task?.current_source && task.status === "RUNNING" ? (
            <span className="app-muted">正在请求：{SOURCE_LABELS[task.current_source] ?? task.current_source}</span>
          ) : null}
          {task?.elapsed_seconds !== null && task?.elapsed_seconds !== undefined ? (
            <span className="app-muted">耗时 {task.elapsed_seconds}s</span>
          ) : null}
          <span className="app-muted">走任务接口：可轮询进度、可取消、结果会与岗位库比对。</span>
        </div>

        {collectProgress.length > 0 ? (
          <ul className="app-progress-list">
            {collectProgress.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}

        {collectResult ? (
          <div className="app-stat-row">
            <span className="app-badge muted">抓到 {collectResult.totals.fetched ?? collectResult.totals.returned}</span>
            <span className="app-badge muted">筛选后 {collectResult.totals.returned}</span>
            <span className="app-badge filled">新增 {collectResult.totals.new ?? 0}</span>
            <span className="app-badge muted">已存在 {collectResult.totals.duplicate ?? 0}</span>
            <span className="app-badge warn">有更新 {collectResult.totals.updated ?? 0}</span>
            <span className="app-badge warn">待确认 {collectResult.totals.needs_review ?? 0}</span>
            <span className="app-badge danger">不可用 {collectResult.totals.failed ?? 0}</span>
            <span className="app-badge filled">可保存 {collectResult.totals.saveable ?? collectResult.jobs.length}</span>
            <span className="app-badge muted">来源成功 {collectResult.totals.sources_ok}</span>
            <span className="app-badge warn">来源失败 {collectResult.totals.sources_failed}</span>
            <span className="app-badge warn">跨来源重复 {collectResult.totals.cross_source_duplicates}</span>
          </div>
        ) : null}
        {collectResult?.warnings?.length ? (
          <p className="app-card-meta">警告：{collectResult.warnings.join("；")}</p>
        ) : null}
      </section>

      {collectResult && collectResult.jobs.length > 0 ? (
        <section className="app-card" aria-label="采集结果">
          <h2 className="app-card-title">2 · 采集结果（{collectResult.jobs.length}）</h2>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th> </th>
                  <th>结果状态</th>
                  <th>岗位</th>
                  <th>企业</th>
                  <th>地点</th>
                  <th>类型</th>
                  <th>JD</th>
                  <th>来源 / 采集时间</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {collectResult.jobs.map((job) => {
                  const key = jobKey(job);
                  const open = expanded.has(key);
                  const status = job.result_status
                    ? RESULT_STATUS_LABEL[job.result_status]
                    : { label: "未比对", tone: "muted", hint: "未选择简历档案，尚未与岗位库比对。" };
                  return (
                    <tr key={key}>
                      <td>
                        <input
                          type="checkbox"
                          checked={selected.has(key)}
                          disabled={job.result_status === "DUPLICATE" && !updateDuplicates}
                          onChange={(event) =>
                            setSelected((prev) => {
                              const next = new Set(prev);
                              if (event.target.checked) next.add(key);
                              else next.delete(key);
                              return next;
                            })
                          }
                          aria-label={`选择 ${job.company} ${job.role}`}
                        />
                      </td>
                      <td>
                        <span className={`app-badge ${status.tone}`} title={job.result_reason ?? status.hint}>
                          {status.label}
                        </span>
                      </td>
                      <td className="cell-title-link">{job.role || "—"}</td>
                      <td>
                        {job.company || "—"}
                        {job.company_is_board_token ? (
                          <span className="app-badge warn" title="该接口未返回公司名，暂用招聘板标识占位">
                            待确认
                          </span>
                        ) : null}
                      </td>
                      <td className="cell-muted">{job.location || "—"}</td>
                      <td className="cell-muted">{EMPLOYMENT_LABEL[job.employment_type ?? "UNKNOWN"] ?? "未标注"}</td>
                      <td className="cell-muted">
                        {open ? (
                          <div className="jd-preview">{job.jd || job.jd_excerpt || "（来源未返回 JD 正文）"}</div>
                        ) : (
                          <button type="button" className="app-btn subtle" onClick={() => setExpanded((prev) => new Set(prev).add(key))}>
                            展开 {((job.jd || job.jd_excerpt || "").length || 0)} 字
                          </button>
                        )}
                      </td>
                      <td className="cell-muted">
                        <a href={job.source_url || "#"} target="_blank" rel="noreferrer">
                          {job.source}
                        </a>
                        <br />
                        {formatTime(job.collected_at)}
                        {job.posted_at ? ` · 发布 ${formatTime(job.posted_at)}` : " · 发布时间未知"}
                      </td>
                      <td className="cell-actions">
                        <button
                          type="button"
                          className="app-btn subtle"
                          disabled={Boolean(rowBusy)}
                          onClick={() => void openMissionFor(job, null, "role", "match")}
                        >
                          {rowBusy.startsWith("match:") ? "处理中…" : "匹配分析"}
                        </button>
                        <button
                          type="button"
                          className="app-btn subtle"
                          disabled={Boolean(rowBusy)}
                          onClick={() => void openMissionFor(job, null, "resume", "resume")}
                        >
                          {rowBusy.startsWith("resume:") ? "处理中…" : "生成岗位定向简历"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="app-row" style={{ marginTop: "0.9rem" }}>
            <button type="button" className="app-btn primary" disabled={saving} onClick={() => void handleSaveSelected()}>
              {saving ? "保存中…" : `批量导入选中岗位（${selected.size}）`}
            </button>
            <label className="app-check-inline">
              <input
                type="checkbox"
                checked={updateDuplicates}
                onChange={(event) => setUpdateDuplicates(event.target.checked)}
              />
              同时更新「有更新」的已有岗位
            </label>
            <span className="app-muted">
              抓到 ≠ 新增：已存在（正文一致）不会重复入库；「有更新」勾选上面这项后才会用新 JD 覆盖旧记录。
            </span>
          </div>
        </section>
      ) : null}

      {/* ---------------------------------------------------------------- 采集当前网页 */}
      <section className="app-card" aria-label="采集当前招聘网页">
        <h2 className="app-card-title">3 · 采集当前招聘网页</h2>
        <p className="app-card-meta">
          复用网申填表那套本地受控浏览器桥：你在浏览器里打开招聘网站、点进单个职位详情页，再回到这里点击采集。
          只读取页面已可见内容，不绕过登录、验证码或任何访问限制；桥只监听 127.0.0.1 并校验令牌与调用来源。
        </p>
        <div className="app-row">
          <span className={`app-badge ${bridge?.available ? "filled" : "warn"}`}>
            {bridge?.available ? `浏览器桥已连接（${bridge.bridge_url}）` : "浏览器桥未启动"}
          </span>
          {bridge?.currentUrl ? <span className="app-muted">当前页：{bridge.currentUrl}</span> : null}
          <button type="button" className="app-btn primary" disabled={captureBusy} onClick={() => void handleCapture()}>
            {captureBusy ? "读取中…" : "采集当前网页"}
          </button>
        </div>
        {!bridge?.available ? (
          <p className="app-card-meta">
            请先运行 <code>start-browser-bridge.cmd</code> 启动受控浏览器桥，再点采集。{bridge?.error ? `（${bridge.error}）` : ""}
          </p>
        ) : null}

        {capture && capture.status !== "OK" ? (
          <p className="app-inline-error" role="alert">
            {capture.note || `无法读取（${capture.status}）`}
            {capture.status === "LISTING_UNSUPPORTED" ? " 也可以复制岗位正文粘贴导入。" : ""}
          </p>
        ) : null}

        {capture?.job && captureDraft ? (
          <div className="app-card nested">
            <h3 className="app-card-title">预览（确认后再入库）</h3>
            <p className="app-card-meta">
              来源：{capture.page_url} · 读取方式：{capture.job.raw?.extraction === "jsonld" ? "页面结构化数据 JobPosting" : "页面可见文本推断"}
            </p>
            <div className="app-filter-row">
              <input value={captureDraft.company} onChange={(event) => setCaptureDraft({ ...captureDraft, company: event.target.value })} placeholder="企业" />
              <input value={captureDraft.role} onChange={(event) => setCaptureDraft({ ...captureDraft, role: event.target.value })} placeholder="岗位" />
              <input value={captureDraft.location} onChange={(event) => setCaptureDraft({ ...captureDraft, location: event.target.value })} placeholder="工作地点" />
            </div>
            <div className="app-chip-row">
              {Object.entries(capture.confidence ?? {}).map(([field, level]) => (
                <span className={`app-chip${level === "MISSING" || level === "LOW" ? " warn" : ""}`} key={field}>
                  {CONFIRM_LABEL[field] ?? field}：{level === "MISSING" ? "待确认" : level === "LOW" ? "低置信" : level === "MEDIUM" ? "中等" : "高"}
                </span>
              ))}
            </div>
            <textarea
              className="app-textarea"
              rows={8}
              value={captureDraft.jd}
              onChange={(event) => setCaptureDraft({ ...captureDraft, jd: event.target.value })}
            />
            <div className="app-row">
              <button type="button" className="app-btn primary" disabled={saving} onClick={() => void handleSaveCapture()}>
                {saving ? "保存中…" : "确认并保存到岗位库"}
              </button>
              <button
                type="button"
                className="app-btn subtle"
                onClick={() => {
                  setCapture(null);
                  setCaptureDraft(null);
                }}
              >
                放弃
              </button>
            </div>
          </div>
        ) : null}
      </section>

      {/* ---------------------------------------------------------------- 手动导入 */}
      <section className="app-card" aria-label="手动导入">
        <h2 className="app-card-title">4 · 手动导入（粘贴 / 链接 / 文件）</h2>
        <div className="app-filter-row">
          {(Object.keys(MODE_LABEL) as IntakeMode[]).map((item) => (
            <button
              type="button"
              key={item}
              className={`app-filter${mode === item ? " active" : ""}`}
              onClick={() => {
                setMode(item);
                setError("");
              }}
            >
              {MODE_LABEL[item]}
            </button>
          ))}
        </div>

        {mode === "paste" ? (
          <div>
            <textarea
              className="app-textarea"
              rows={8}
              value={pasteText}
              onChange={(event) => setPasteText(event.target.value)}
              placeholder="把完整 JD 粘贴到这里，支持一次粘贴多条岗位。"
            />
            <div className="app-row" style={{ marginTop: "0.7rem" }}>
              <button type="button" className="app-btn primary" disabled={busy === "paste"} onClick={() => void handlePaste()}>
                {busy === "paste" ? "解析中…" : "解析并保存到岗位库"}
              </button>
            </div>
          </div>
        ) : null}

        {mode === "url" ? (
          <div>
            <div className="app-row">
              <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https:// 公开招聘页面地址" />
              <button type="button" className="app-btn primary" disabled={busy === "url"} onClick={() => void handleUrl()}>
                {busy === "url" ? "采集中…" : "采集并保存"}
              </button>
            </div>
            <p className="app-card-meta">
              只抓取公开可访问的页面；遇到登录、验证码或访问限制会明确提示「不支持自动采集」，请改用手动粘贴，系统不做任何绕过。
            </p>
          </div>
        ) : null}

        {mode === "file" ? (
          <div>
            <input
              type="file"
              accept=".pdf,.txt,.md,.docx,.doc,.png,.jpg,.jpeg,.webp"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void handleFile(file);
              }}
            />
            <p className="app-card-meta">PDF / 文本 / Word 可直接解析；图片暂不支持自动 OCR，请复制成文本后粘贴。</p>
          </div>
        ) : null}
      </section>

      {/* ---------------------------------------------------------------- 岗位库 */}
      <section className="app-card" aria-label="岗位库">
        <h2 className="app-card-title">5 · 已保存岗位（{library.length}）</h2>
        <div className="app-filter-row">
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="关键词：公司 / 岗位 / 原文" />
          <select
            value={company}
            onChange={(event) => {
              setCompany(event.target.value);
              applyFilters({ company: event.target.value });
            }}
          >
            <option value="">全部公司</option>
            {facets.companies.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={location}
            onChange={(event) => {
              setLocation(event.target.value);
              applyFilters({ location: event.target.value });
            }}
          >
            <option value="">全部地点</option>
            {facets.locations.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={kind}
            onChange={(event) => {
              setKind(event.target.value);
              applyFilters({ kind: event.target.value });
            }}
          >
            <option value="">全部类型</option>
            <option value="candidate">候选草稿</option>
            <option value="mission">正式岗位</option>
          </select>
          <button type="button" className="app-btn" onClick={() => applyFilters()}>
            筛选
          </button>
          <button
            type="button"
            className="app-btn subtle"
            onClick={() => {
              setKeyword("");
              setCompany("");
              setLocation("");
              setKind("");
              void refreshLibrary(profileId, {});
            }}
          >
            重置
          </button>
        </div>

        {library.length === 0 ? (
          <p className="app-empty">岗位库还是空的，先用上面的入口导入或采集一个岗位。</p>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>类型</th>
                  <th>公司</th>
                  <th>岗位</th>
                  <th>地点</th>
                  <th>来源</th>
                  <th>解析状态</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {library.map((item) => {
                  const missionId = item.imported_mission_id ?? (item.kind === "MISSION" ? item.id : null);
                  return (
                    <tr key={`${item.kind}-${item.id}`}>
                      <td>
                        <span className={`app-badge ${item.kind === "MISSION" ? "filled" : "muted"}`}>
                          {item.kind === "MISSION" ? "正式岗位" : "候选草稿"}
                        </span>
                      </td>
                      <td>{item.company ?? "—"}</td>
                      <td className="cell-title-link">{item.role ?? "—"}</td>
                      <td className="cell-muted">{item.location ?? "—"}</td>
                      <td className="cell-muted">
                        {item.source_url ? (
                          <a href={item.source_url} target="_blank" rel="noreferrer">
                            {item.source_kind ?? "链接"}
                          </a>
                        ) : (
                          (item.source_kind ?? "手动")
                        )}
                      </td>
                      <td>
                        <span className={`app-badge ${item.parse_status === "NEEDS_CONFIRM" ? "warn" : "muted"}`}>{item.parse_status}</span>
                      </td>
                      <td className="cell-actions">
                        {missionId ? (
                          <>
                            <Link className="app-btn subtle" href={missionHref(missionId, "role")}>
                              匹配分析
                            </Link>
                            <Link className="app-btn subtle" href={missionHref(missionId, "resume")}>
                              生成岗位定向简历
                            </Link>
                          </>
                        ) : (
                          <>
                            <button
                              type="button"
                              className="app-btn subtle"
                              disabled={busy === `import:${item.id}`}
                              onClick={() => void openMissionFor(null, item.id, "role", "match")}
                            >
                              {busy === `import:${item.id}` ? "导入中…" : "导入并匹配分析"}
                            </button>
                            <button
                              type="button"
                              className="app-btn subtle"
                              disabled={busy === `import:${item.id}`}
                              onClick={() => void openMissionFor(null, item.id, "resume", "resume")}
                            >
                              生成岗位定向简历
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
