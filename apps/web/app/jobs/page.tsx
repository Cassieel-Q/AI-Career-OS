"use client";

import Link from "next/link";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { readCurrentProfileId } from "../career-hub.ts";
import { missionHref, PROFILE_STORAGE_KEY } from "../missions.ts";
import {
  extractJobFile,
  fetchJobUrl,
  importCandidateJob,
  parseCandidateJobs,
  readJobLibrary,
  readProfiles,
  type LibraryItem,
} from "../jobs.ts";

type IntakeMode = "paste" | "url" | "file";

const MODE_LABEL: Record<IntakeMode, string> = {
  paste: "粘贴完整 JD",
  url: "公开招聘链接",
  file: "岗位截图 / PDF / 文档",
};

export default function JobsPage() {
  const router = useRouter();
  const [profileId, setProfileId] = useState("");

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
    if (pid) {
      void refreshLibrary(pid, {});
      return;
    }
    // 本地没有档案 ID（例如首次打开/清了浏览器数据）：自动取第一个档案并记住，
    // 否则岗位库会永远显示为空。
    void (async () => {
      try {
        const response = await readProfiles();
        const profiles = Array.isArray(response?.profiles) ? response.profiles : [];
        if (!profiles.length) {
          setError("还没有简历档案，请先到「简历」上传简历。");
          return;
        }
        const first = String(profiles[0].id || "");
        window.localStorage.setItem(PROFILE_STORAGE_KEY, first);
        setProfileId(first);
        setInfo(`已自动选择档案${profiles[0].full_name ? `：${profiles[0].full_name}` : ""}。`);
        void refreshLibrary(first, {});
      } catch {
        setError("读取档案列表失败，请确认本机服务已启动。");
      }
    })();
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


  /** 候选草稿 → 导入正式岗位 → 跳到对应 Mission 页签。 */
  const openMissionFor = useCallback(
    async (candidateId: string, tab: "role" | "resume", label: string) => {
      if (!requireProfile()) return;
      setBusy(`import:${candidateId}`);
      setError("");
      try {
        const imported = await importCandidateJob(candidateId);
        applyFilters();
        router.push(missionHref(imported.mission_id, tab));
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "打开岗位工作台失败。");
      } finally {
        setBusy("");
      }
    },
    [applyFilters, profileId, router],
  );

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

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Job Intake</p>
          <h1 className="app-page-title">岗位导入与岗位库</h1>
          <p className="app-page-subtitle">
            手动导入或用浏览器扩展从 BOSS 直聘采集岗位；保存后进入岗位库，点「匹配分析」开始优化。
          </p>
        </div>
        <Link className="app-btn primary" href={"/jobs/import" as Route}>
          导入 BOSS 直聘岗位 →
        </Link>
      </header>

      {error && (
        <p className="app-inline-error" role="alert">
          {error}
        </p>
      )}
      {info && <p className="app-muted">{info}</p>}

      {/* ---------------------------------------------------------------- 手动导入 */}
      <section className="app-card" aria-label="手动导入">
        <h2 className="app-card-title">1 · 手动导入（粘贴 / 链接 / 文件）</h2>
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
        <h2 className="app-card-title">2 · 已保存岗位（{library.length}）</h2>
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
                              onClick={() => void openMissionFor(item.id, "role", "match")}
                            >
                              {busy === `import:${item.id}` ? "导入中…" : "导入并匹配分析"}
                            </button>
                            <button
                              type="button"
                              className="app-btn subtle"
                              disabled={busy === `import:${item.id}`}
                              onClick={() => void openMissionFor(item.id, "resume", "resume")}
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
