"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { readCurrentProfileId } from "../career-hub.ts";
import {
  collectRemoteOk,
  extractJobFile,
  fetchJobUrl,
  importCandidateJob,
  parseCandidateJobs,
  readJobLibrary,
  readJobSources,
  saveCollectedJobs,
  type CollectedJob,
  type JobSource,
  type LibraryItem,
} from "../jobs.ts";

type IntakeMode = "paste" | "url" | "file" | "remoteok";

const MODE_LABEL: Record<IntakeMode, string> = {
  paste: "粘贴完整 JD",
  url: "公开招聘链接",
  file: "岗位截图 / PDF / 文档",
  remoteok: "RemoteOK 公开接口",
};

export default function JobsPage() {
  const [profileId, setProfileId] = useState("");
  const [sources, setSources] = useState<JobSource[]>([]);
  const [mode, setMode] = useState<IntakeMode>("paste");
  const [pasteText, setPasteText] = useState("");
  const [url, setUrl] = useState("");
  const [remoteTag, setRemoteTag] = useState("");
  const [remoteLimit, setRemoteLimit] = useState(10);
  const [collected, setCollected] = useState<CollectedJob[]>([]);
  const [selectedCollected, setSelectedCollected] = useState<Set<string>>(new Set());
  const [library, setLibrary] = useState<LibraryItem[]>([]);
  const [facets, setFacets] = useState<{ companies: string[]; locations: string[] }>({ companies: [], locations: [] });
  const [keyword, setKeyword] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [kind, setKind] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const refreshLibrary = useCallback(async (pid: string, filters: { q?: string; company?: string; location?: string; kind?: string }) => {
    if (!pid) return;
    try {
      const result = await readJobLibrary(pid, filters);
      setLibrary(result.items);
      setFacets(result.facets);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取岗位库失败。");
    }
  }, []);

  useEffect(() => {
    const pid = readCurrentProfileId();
    setProfileId(pid);
    void readJobSources()
      .then((result) => setSources(result.sources))
      .catch(() => setSources([]));
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

  const handleCollect = useCallback(async () => {
    setBusy("collect");
    setError("");
    setCollected([]);
    try {
      const result = await collectRemoteOk(remoteTag, remoteLimit);
      if (result.status !== "OK") {
        setError(result.note || `采集未返回结果（状态：${result.status}）`);
        return;
      }
      setCollected(result.jobs);
      setSelectedCollected(new Set(result.jobs.map((job) => job.source_url)));
      setInfo(`从 RemoteOK 公开接口采集到 ${result.jobs.length} 条真实岗位，勾选后可保存进岗位库。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "采集失败。");
    } finally {
      setBusy("");
    }
  }, [remoteLimit, remoteTag]);

  const handleSaveCollected = useCallback(async () => {
    if (!requireProfile()) return;
    const jobs = collected.filter((job) => selectedCollected.has(job.source_url));
    if (!jobs.length) {
      setError("没有勾选任何采集结果。");
      return;
    }
    setBusy("save");
    setError("");
    try {
      const result = await saveCollectedJobs(profileId, jobs);
      setInfo(`保存 ${result.saved_count} 条，跳过重复 ${result.skipped_count} 条。`);
      applyFilters();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败。");
    } finally {
      setBusy("");
    }
  }, [applyFilters, collected, profileId, selectedCollected]);

  const handleImport = useCallback(
    async (item: LibraryItem) => {
      setBusy(`import:${item.id}`);
      setError("");
      try {
        const result = await importCandidateJob(item.id);
        setInfo(`已导入为正式岗位：${result.company} · ${result.role}。可进入岗位工作台开始简历优化。`);
        applyFilters();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "导入岗位失败。");
      } finally {
        setBusy("");
      }
    },
    [applyFilters],
  );

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Job Intake</p>
          <h1 className="app-page-title">岗位</h1>
          <p className="app-page-subtitle">
            统一入口：粘贴 JD、公开链接、截图 / PDF / 文档，或用公开接口采集。保存进岗位库后可直接进入简历优化流程。
          </p>
        </div>
      </header>

      {error && (
        <p className="app-inline-error" role="alert">
          {error}
        </p>
      )}
      {info && <p className="app-muted">{info}</p>}

      <section className="app-card" aria-label="岗位入口">
        <h2 className="app-card-title">1 · 导入岗位</h2>
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

        {sources.length > 0 ? (
          <p className="app-card-meta">{sources.find((item) => item.id === mode)?.note}</p>
        ) : null}

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

        {mode === "remoteok" ? (
          <div>
            <div className="app-row">
              <input value={remoteTag} onChange={(event) => setRemoteTag(event.target.value)} placeholder="关键词（可选），如 product manager" />
              <input
                type="number"
                min={1}
                max={50}
                value={remoteLimit}
                onChange={(event) => setRemoteLimit(Number(event.target.value) || 10)}
                style={{ maxWidth: "7rem" }}
              />
              <button type="button" className="app-btn primary" disabled={busy === "collect"} onClick={() => void handleCollect()}>
                {busy === "collect" ? "采集中…" : "采集真实岗位"}
              </button>
            </div>
            <p className="app-card-meta">数据来自 RemoteOK 官方公开 JSON 接口（无需登录），采集结果会记录来源链接与采集时间。</p>
          </div>
        ) : null}
      </section>

      {collected.length > 0 ? (
        <section className="app-card" aria-label="采集结果">
          <h2 className="app-card-title">2 · 采集结果（{collected.length}）</h2>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th> </th>
                  <th>公司</th>
                  <th>岗位</th>
                  <th>地点</th>
                  <th>来源</th>
                  <th>采集时间</th>
                </tr>
              </thead>
              <tbody>
                {collected.map((job) => (
                  <tr key={job.source_url}>
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedCollected.has(job.source_url)}
                        onChange={(event) =>
                          setSelectedCollected((prev) => {
                            const next = new Set(prev);
                            if (event.target.checked) next.add(job.source_url);
                            else next.delete(job.source_url);
                            return next;
                          })
                        }
                        aria-label={`选择 ${job.company} ${job.role}`}
                      />
                    </td>
                    <td>{job.company}</td>
                    <td className="cell-title-link">{job.role}</td>
                    <td className="cell-muted">{job.location}</td>
                    <td className="cell-muted">
                      <a href={job.source_url} target="_blank" rel="noreferrer">
                        {job.source}
                      </a>
                    </td>
                    <td className="cell-muted">{new Date(job.collected_at).toLocaleString("zh-CN")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="app-row" style={{ marginTop: "0.9rem" }}>
            <button type="button" className="app-btn primary" disabled={busy === "save"} onClick={() => void handleSaveCollected()}>
              {busy === "save" ? "保存中…" : `保存选中岗位（${selectedCollected.size}）`}
            </button>
            <span className="app-muted">重复岗位会自动跳过并说明原因。</span>
          </div>
        </section>
      ) : null}

      <section className="app-card" aria-label="岗位库">
        <h2 className="app-card-title">3 · 已保存岗位（{library.length}）</h2>
        <div className="app-filter-row">
          <input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="关键词：公司 / 岗位 / 原文" />
          <select value={company} onChange={(event) => { setCompany(event.target.value); applyFilters({ company: event.target.value }); }}>
            <option value="">全部公司</option>
            {facets.companies.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select value={location} onChange={(event) => { setLocation(event.target.value); applyFilters({ location: event.target.value }); }}>
            <option value="">全部地点</option>
            {facets.locations.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select value={kind} onChange={(event) => { setKind(event.target.value); applyFilters({ kind: event.target.value }); }}>
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
          <p className="app-empty">岗位库还是空的，先用上面的入口导入一个岗位。</p>
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
                {library.map((item) => (
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
                      <span className="app-badge muted">{item.parse_status}</span>
                    </td>
                    <td className="cell-actions">
                      {item.kind === "MISSION" || item.imported_mission_id ? (
                        <Link
                          className="app-btn subtle"
                          href={`/missions/${item.imported_mission_id ?? item.id}` as never}
                        >
                          进入岗位工作台
                        </Link>
                      ) : (
                        <button
                          type="button"
                          className="app-btn subtle"
                          disabled={busy === `import:${item.id}`}
                          onClick={() => void handleImport(item)}
                        >
                          {busy === `import:${item.id}` ? "导入中…" : "导入为正式岗位"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
