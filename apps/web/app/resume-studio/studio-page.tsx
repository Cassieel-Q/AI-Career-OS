"use client";
/* eslint-disable @next/next/no-img-element -- Typst supplies complete data-URL SVG pages; Next image optimization cannot process these previews. */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  applyStudioOperation, confirmStudio, downloadStudioExport, downloadStudioPdf, readStudio, readStudioSourceDiff, readStudioTemplates, reimportStudio,
  renderStudio, StudioApiError,
} from "./api.ts";
import { emptyHistory, findNode, inverseOperation, recordHistory, redoHistory, replayOperation, undoHistory } from "./history.ts";
import type { StudioHistory } from "./history.ts";
import { moveSection, normalizeLayout, sectionLabel } from "./layout-config.ts";
import type { StudioNode, StudioOperation, StudioPreview, StudioSourceDiff, StudioState, StudioTemplate } from "./types.ts";
import { bindMissionResumePdf, writeResumeBound } from "../missions.ts";
import "./studio.css";

type FactFilter = "ALL" | StudioNode["claim_status"];
type SamplePreview = { pages: string[]; page_count: number };
const FACTS: { key: FactFilter; label: string }[] = [
  { key: "ALL", label: "全部" }, { key: "CONFIRMED", label: "已核对" },
  { key: "NEEDS_CONFIRMATION", label: "待核对" }, { key: "BLOCKED_MISSING", label: "缺失" },
  { key: "OMITTED", label: "已省略" },
];
const STATUS_LABEL: Record<StudioNode["claim_status"], string> = {
  CONFIRMED: "已核对", NEEDS_CONFIRMATION: "待核对", BLOCKED_MISSING: "缺失", OMITTED: "已省略",
};
const svgUrl = (svg: string) => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
const pageWidth = (svg: string) => Number(svg.match(/<svg[^>]*width="([\d.]+)/)?.[1] || 595);
const pageHeight = (svg: string) => Number(svg.match(/<svg[^>]*height="([\d.]+)/)?.[1] || 842);

function describeError(error: unknown): string {
  if (error instanceof StudioApiError) {
    const detail = error.detail as { message?: string; checks?: { message: string }[] };
    return detail?.checks?.map(item => item.message).join("；") || detail?.message || error.message;
  }
  return error instanceof Error ? error.message : "操作失败，请重试。";
}

function nodesOf(state: StudioState): StudioNode[] {
  return [
    ...Object.values(state.document.basics),
    ...state.document.sections.flatMap(section => [section.title, ...section.entries.flatMap(entry => [entry.title, entry.subtitle, entry.date, entry.location, ...entry.bullets])]),
  ];
}

export function StudioPage({ missionId }: { missionId: string }) {
  const [state, setState] = useState<StudioState | null>(null);
  const [templates, setTemplates] = useState<StudioTemplate[]>([]);
  const [sourceDiff, setSourceDiff] = useState<StudioSourceDiff | null>(null);
  const [preview, setPreview] = useState<StudioPreview | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [gallery, setGallery] = useState(false);
  const [galleryLanguage, setGalleryLanguage] = useState<"zh" | "en">("zh");
  const [samples, setSamples] = useState<Record<string, SamplePreview>>({});
  const [sampleOpen, setSampleOpen] = useState<string | null>(null);
  const [factFilter, setFactFilter] = useState<FactFilter>("ALL");
  const [sourceOpen, setSourceOpen] = useState(false);
  const [history, setHistory] = useState<StudioHistory>(emptyHistory);
  const [mobileTab, setMobileTab] = useState<"preview" | "edit">("preview");
  const previewSeq = useRef(0);
  const sampleLoading = useRef(new Set<string>());
  const draftRef = useRef("");
  const dragId = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const loaded = await readStudio(missionId);
      const [catalog, difference] = await Promise.all([readStudioTemplates(), readStudioSourceDiff(missionId)]);
      setState(loaded);
      setTemplates(catalog);
      setSourceDiff(difference);
      setGalleryLanguage(loaded.language);
      setError("");
    } catch (caught) { setError(describeError(caught)); }
  }, [missionId]);
  useEffect(() => { void load(); }, [load]);

  const revision = state?.revision;
  useEffect(() => {
    if (revision == null) return;
    const seq = ++previewSeq.current;
    const timer = setTimeout(() => {
      setRendering(true);
      void renderStudio(missionId, revision).then(result => {
        if (seq === previewSeq.current) { setPreview(result); setError(""); }
      }).catch(caught => {
        if (seq === previewSeq.current) setError(`预览失败：${describeError(caught)}。已保留上次成功预览。`);
      }).finally(() => { if (seq === previewSeq.current) setRendering(false); });
    }, 300);
    return () => clearTimeout(timer);
  }, [missionId, revision]);

  useEffect(() => {
    if (!gallery || templates.length === 0) return;
    const missing = templates.filter(item => item.language === galleryLanguage && !samples[item.id] && !sampleLoading.current.has(item.id));
    if (!missing.length) return;
    void Promise.all(missing.map(async item => {
      sampleLoading.current.add(item.id);
      try {
        const url = (item.sample_preview_url as string) || `/api/v1/resume-studio/templates/${item.id}/sample-preview`;
        const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
        const result = await fetch(`${base}${url}`).then(async response => {
          if (!response.ok) throw new Error(`${response.status}`);
          return response.json() as Promise<SamplePreview>;
        });
        setSamples(previous => ({ ...previous, [item.id]: result }));
      } catch { /* One card can retry when gallery reopens. */ }
      finally { sampleLoading.current.delete(item.id); }
    }));
  }, [gallery, galleryLanguage, templates, samples]);

  const selected = state && selectedId ? findNode(state.document, selectedId) : null;
  useEffect(() => {
    if (selected && draftRef.current === "") { setDraft(selected.text); draftRef.current = selected.text; }
  }, [selected]);
  const choose = (id: string) => {
    const node = state && findNode(state.document, id);
    if (!node) return;
    setSelectedId(id); setDraft(node.text); draftRef.current = node.text;
    setSourceOpen(false); setMobileTab("edit");
  };

  const mutate = async (operation: StudioOperation, record = true) => {
    if (!state || busy) return false;
    const previous = state;
    setBusy(true); setError(""); setMessage("");
    try {
      const next = await applyStudioOperation(missionId, previous.revision, operation);
      setState(next);
      if (record) {
        const inverse = inverseOperation(previous, operation, next);
        if (inverse) {
          const forward = replayOperation(operation, inverse);
          setHistory(current => recordHistory(current, { forward, inverse }));
        }
      }
      return true;
    } catch (caught) {
      setError(describeError(caught));
      if (caught instanceof StudioApiError && caught.status === 409) setMessage("另一个窗口已更新简历。当前输入仍在编辑框中，可复制后点“重新读取”。");
      return false;
    } finally { setBusy(false); }
  };

  const saveDraft = async () => {
    if (!selected || draft === selected.text) return;
    const success = await mutate({ type: "set_text", node_id: selected.id, text: draft });
    if (success) { setMessage("已保存并重新排版。"); draftRef.current = draft; }
  };
  const doUndo = async () => {
    const [operation, next] = undoHistory(history);
    if (operation && await mutate(operation, false)) setHistory(next);
  };
  const doRedo = async () => {
    const [operation, next] = redoHistory(history);
    if (operation && await mutate(operation, false)) setHistory(next);
  };
  const move = (id: string, group: { id: string }[], delta: -1 | 1) => {
    const index = group.findIndex(item => item.id === id);
    const target = index + delta;
    if (index < 0 || target < 0 || target >= group.length) return;
    void mutate({ type: "move", node_id: id, before_id: delta < 0 ? group[target].id : group[target + 1]?.id });
  };
  const drop = (targetId: string) => {
    if (dragId.current && dragId.current !== targetId) void mutate({ type: "move", node_id: dragId.current, before_id: targetId });
    dragId.current = null;
  };
  const confirm = async () => {
    if (!state) return;
    setBusy(true); setError("");
    try {
      const next = await confirmStudio(missionId, state.revision);
      setState(next); setMessage("当前修订版已确认，可以下载投递版 PDF。");
    } catch (caught) { setError(describeError(caught)); }
    finally { setBusy(false); }
  };
  const reimport = async () => {
    if (!state || !sourceDiff?.update_available) return;
    const summary = `新版已确认改写稿有 ${sourceDiff.added_bullets?.length || 0} 条新增、${sourceDiff.removed_bullets?.length || 0} 条移除要点。重新导入会替换当前工作台精修内容，并生成新修订版。`;
    if (!window.confirm(`${summary}\n\n确定重新导入？`)) return;
    setBusy(true); setError("");
    try {
      const next = await reimportStudio(missionId, state.revision);
      setState(next); setSourceDiff({ update_available: false, current_source_id: next.source_target_resume_id });
      setHistory(emptyHistory()); setSelectedId(null); setDraft(""); draftRef.current = "";
      setMessage("已从新版已确认改写稿重新导入。请重新核对并确认投递版。");
    } catch (caught) { setError(describeError(caught)); }
    finally { setBusy(false); }
  };
  const download = async () => {
    try {
      const { blob, filename } = await downloadStudioPdf(missionId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) { setError(describeError(caught)); }
  };
  const overwriteResume = async () => {
    if (!state) return;
    if (!window.confirm("将用这份投递版 PDF 覆盖当前岗位简历，覆盖后直接进入模拟面试。确定继续？")) return;
    setBusy(true); setError("");
    try {
      const { blob, filename } = await downloadStudioPdf(missionId);
      const file = new File([blob], filename, { type: "application/pdf" });
      const bound = await bindMissionResumePdf(missionId, file);
      try {
        writeResumeBound(missionId, "upload");
      } catch { /* localStorage unavailable — non-blocking */ }
      // One step: overwrite done → go straight into the mock interview session.
      const pid = bound.bound_profile_id || bound.profile_id;
      window.location.assign(`/proof/${encodeURIComponent(pid)}/interview?mission_id=${encodeURIComponent(missionId)}&fresh=1`);
    } catch (caught) { setError(describeError(caught)); }
    finally { setBusy(false); }
  };
  const downloadText = async (format: "markdown" | "txt" | "json") => {
    try {
      const { blob, filename } = await downloadStudioExport(missionId, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) { setError(describeError(caught)); }
  };

  const factNodes = useMemo(() => state ? nodesOf(state).filter(node => factFilter === "ALL" || node.claim_status === factFilter) : [], [state, factFilter]);
  const activeTemplate = templates.find(item => item.id === state?.template_id);
  const canDownload = Boolean(state && state.confirmed_revision === state.revision);

  if (!state) return <main className="rs-loading"><p>AI CAREER OS / RESUME STUDIO</p><h1>正在打开简历工作台</h1>{error && <p role="alert">{error}</p>}<Link href={`/missions/${missionId}/resume`}>返回简历优化</Link></main>;

  const layout = normalizeLayout(state.layout_config);
  const patchLayout = (patch: Partial<typeof layout>) => void mutate({ type: "set_layout", layout_config: normalizeLayout({ ...layout, ...patch }) });

  return <main className="rs-root">
    <header className="rs-topbar">
      <div className="rs-brand"><span className="rs-logo">A<span>•</span></span><div><strong>AI CAREER OS</strong><small>RESUME STUDIO / 简历工作台</small></div></div>
      <div className="rs-top-actions"><span className="rs-revision">修订版 {state.revision}{canDownload ? " · 已确认" : " · 编辑中"}</span><Link href={`/missions/${missionId}/resume`}>返回简历优化 ↗</Link></div>
    </header>
    <div className="rs-stage"><span>01 内容</span><span>02 模板</span><span>03 事实核对</span><span>04 投递版</span></div>
    <div className="rs-toolbar">
      <div><p className="rs-kicker">FINAL RESUME / 排版与精修</p><h1>把确认过的经历，排成一份可投递的简历。</h1><p>点击页面文字直接修改。每次保存会生成新的修订版，预览和 PDF 始终使用同一份内容。</p></div>
      <div className="rs-toolbar-buttons"><button type="button" className="rs-secondary" onClick={() => setGallery(true)}>选择模板 <b>{activeTemplate?.name || state.template_id}</b></button><button type="button" className="rs-secondary" onClick={() => void doUndo()} disabled={!history.undo.length || busy}>撤销</button><button type="button" className="rs-secondary" onClick={() => void doRedo()} disabled={!history.redo.length || busy}>重做</button></div>
    </div>
    {(error || message) && <div className={error ? "rs-alert rs-alert-error" : "rs-alert"} role={error ? "alert" : "status"}>{error || message}{error && <button type="button" onClick={() => void load()}>重新读取</button>}</div>}
    {sourceDiff?.update_available && <div className="rs-source-update" role="status"><div><strong>发现新版已确认改写稿</strong><p>新增 {sourceDiff.added_bullets?.length || 0} 条、移除 {sourceDiff.removed_bullets?.length || 0} 条要点。当前精修版会一直保留，直到你主动重新导入。</p><details><summary>查看差异</summary><p>新增：{sourceDiff.added_bullets?.join("；") || "无"}</p><p>移除：{sourceDiff.removed_bullets?.join("；") || "无"}</p></details></div><button type="button" disabled={busy} onClick={() => void reimport()}>重新导入新版</button></div>}
    <div className="rs-mobile-tabs"><button type="button" className={mobileTab === "preview" ? "active" : ""} onClick={() => setMobileTab("preview")}>页面预览</button><button type="button" className={mobileTab === "edit" ? "active" : ""} onClick={() => setMobileTab("edit")}>内容编辑</button></div>
    <div className="rs-workbench">
      <aside className={`rs-outline ${mobileTab === "preview" ? "rs-mobile-hidden" : ""}`}>
        <div className="rs-panel-heading"><span>01 / CONTENT</span><h2>简历内容</h2><small>拖动或使用箭头调整同一板块内的顺序</small></div>
        <div className="rs-basics"><strong>基本信息</strong>{Object.entries(state.document.basics).map(([key, node]) => <button type="button" key={node.id} className={selectedId === node.id ? "rs-row selected" : "rs-row"} onClick={() => choose(node.id)}><span>{({ name: "姓名", phone: "电话", email: "邮箱", location: "地点" } as Record<string, string>)[key] || key}</span><b>{node.text || "待填写"}</b></button>)}</div>
        {state.document.sections.map(section => <div className="rs-section-list" key={section.id}>
          <div className="rs-section-title"><button type="button" onClick={() => choose(section.title.id)}>{section.title.text}</button><button type="button" aria-label={`新增${section.title.text}`} onClick={() => { const title = window.prompt("新增条目名称"); if (title?.trim()) void mutate({ type: "add_entry", section_id: section.id, title: title.trim() }); }}>＋</button></div>
          {section.entries.map(entry => <div key={entry.id} className={`rs-entry ${entry.status === "OMITTED" ? "omitted" : ""}`} draggable onDragStart={() => { dragId.current = entry.id; }} onDragOver={event => event.preventDefault()} onDrop={() => drop(entry.id)}>
            <div className="rs-entry-head"><button type="button" className="rs-entry-name" onClick={() => choose(entry.title.id)}>{entry.title.text || "未命名"}</button><span className="rs-move"><button type="button" aria-label="上移" onClick={() => move(entry.id, section.entries, -1)}>↑</button><button type="button" aria-label="下移" onClick={() => move(entry.id, section.entries, 1)}>↓</button></span></div>
            <button type="button" className="rs-subline" onClick={() => choose(entry.subtitle.id)}>{entry.subtitle.text || "添加单位/说明"}</button>
            <div className="rs-entry-meta"><button type="button" onClick={() => choose(entry.date.id)}>{entry.date.text || "填写日期"}</button><button type="button" onClick={() => void mutate({ type: entry.status === "OMITTED" ? "restore" : "omit", node_id: entry.id })}>{entry.status === "OMITTED" ? "恢复" : "省略"}</button></div>
            {entry.bullets.map(bullet => <div className={`rs-bullet ${bullet.claim_status === "OMITTED" ? "omitted" : ""}`} key={bullet.id} draggable onDragStart={() => { dragId.current = bullet.id; }} onDragOver={event => event.preventDefault()} onDrop={() => drop(bullet.id)}><button type="button" className="rs-bullet-text" onClick={() => choose(bullet.id)}>• {bullet.text || "待填写要点"}</button><button type="button" aria-label="省略或恢复要点" onClick={() => void mutate({ type: bullet.claim_status === "OMITTED" ? "restore" : "omit", node_id: bullet.id })}>{bullet.claim_status === "OMITTED" ? "↺" : "×"}</button></div>)}
            <button type="button" className="rs-add-bullet" onClick={() => { const text = window.prompt("新增经历要点"); if (text?.trim()) void mutate({ type: "add_bullet", entry_id: entry.id, text: text.trim() }); }}>＋ 添加要点</button>
          </div>)}
        </div>)}
      </aside>
      <section className={`rs-preview-panel ${mobileTab === "edit" ? "rs-mobile-hidden" : ""}`} aria-label="简历实际页面预览">
        <div className="rs-preview-heading"><div><span>02 / LIVE PREVIEW</span><h2>实际页面预览</h2></div><small>{rendering ? "正在排版…" : `${preview?.page_count ?? "—"} 页 · ${activeTemplate?.name || state.template_id}`}</small></div>
        <div className="rs-pages">{preview?.pages.map((svg, index) => <div className="rs-page" key={`${preview.revision}-${index}`}><img src={svgUrl(svg)} alt={`简历第 ${index + 1} 页`} draggable={false} />{preview.layout_map.filter(item => item.page === index + 1).map(item => <button type="button" key={item.id} aria-label={`编辑 ${findNode(state.document, item.id)?.text || "文字"}`} title="点击编辑" className={`rs-hotspot ${selectedId === item.id ? "selected" : ""}`} style={{ left: `${item.x / pageWidth(svg) * 100}%`, top: `${item.y / pageHeight(svg) * 100}%`, width: `${item.width / pageWidth(svg) * 100}%`, height: `${Math.max(item.height, 13) / pageHeight(svg) * 100}%` }} onClick={() => choose(item.id)} />)}<div className="rs-page-number">{String(index + 1).padStart(2, "0")}</div></div>)}{!preview && <div className="rs-page-placeholder">正在生成真实页面预览…</div>}</div>
      </section>
      <aside className={`rs-inspector ${mobileTab === "preview" ? "rs-mobile-hidden" : ""}`}>
        <div className="rs-panel-heading"><span>03 / INSPECTOR</span><h2>{selected ? "编辑所选内容" : "事实与导出"}</h2><small>{selected ? "保存后立即重新排版" : "核对高风险事实后生成 PDF"}</small></div>
        {selected ? <div className="rs-edit-card"><div className="rs-edit-top"><span className={`rs-fact-badge ${selected.claim_status.toLowerCase()}`}>{STATUS_LABEL[selected.claim_status]}</span><span>{selected.risk_level === "HIGH" ? "高风险事实" : "普通内容"}</span></div><label htmlFor="rs-edit-text">文字内容</label><textarea id="rs-edit-text" value={draft} onChange={event => { setDraft(event.target.value); draftRef.current = event.target.value; }} rows={Math.max(3, Math.min(8, Math.ceil(draft.length / 25)))} /><div className="rs-edit-actions"><button type="button" onClick={() => void saveDraft()} disabled={busy || draft === selected.text}>保存修改</button><button type="button" className="rs-secondary" onClick={() => { setDraft(selected.text); draftRef.current = selected.text; }}>放弃输入</button></div><button type="button" className="rs-source-toggle" onClick={() => setSourceOpen(value => !value)}>来源与事实状态 {sourceOpen ? "⌃" : "⌄"}</button>{sourceOpen && <div className="rs-source"><p>来源：{selected.source_kind}{selected.source_id ? ` / ${selected.source_id}` : " / 新增内容"}</p><p>证据引用：{selected.evidence_refs.length ? selected.evidence_refs.join("、") : "尚未关联"}</p><p>修改后的事实需重新核对，模板切换不会改变此状态。</p></div>}{selected.claim_status !== "CONFIRMED" && selected.claim_status !== "OMITTED" && <button type="button" className="rs-confirm-fact" onClick={() => void mutate({ type: "confirm_fact", node_id: selected.id }, false)}>我已核对这项事实</button>}{selected.claim_status === "OMITTED" && <button type="button" onClick={() => void mutate({ type: "restore", node_id: selected.id })}>恢复这项内容</button>}</div> : <div className="rs-inspector-empty"><span>✳</span><p>从左侧列表或中央页面选择任意文字，开始精修。</p></div>}
        <div className="rs-facts"><div className="rs-facts-heading"><h3>事实状态</h3><span>{factNodes.length} 项</span></div><div className="rs-fact-filters">{FACTS.map(item => <button key={item.key} type="button" className={factFilter === item.key ? "active" : ""} onClick={() => setFactFilter(item.key)}>{item.label}</button>)}</div><div className="rs-fact-list">{factNodes.filter(node => node.text || node.claim_status === "BLOCKED_MISSING").slice(0, 24).map(node => <button type="button" key={node.id} onClick={() => choose(node.id)}><span className={`rs-fact-dot ${node.claim_status.toLowerCase()}`} /><span>{node.text || "缺失内容"}</span></button>)}</div></div>
        <div className="rs-layout" aria-label="版式设置"><h3>版式设置</h3><p>预览、PDF、Word、Markdown 使用同一份版式；改动会生成新修订版。</p><div className="layout-controls">
          <label>强调色<input type="color" value={layout.accent_color} onChange={event => patchLayout({ accent_color: event.target.value })} /></label>
          <label>字号倍数<input type="number" min={0.6} max={1.6} step={0.05} value={layout.font_scale} onChange={event => patchLayout({ font_scale: Number(event.target.value) })} /></label>
          <label>行高<input type="number" min={1} max={2.5} step={0.05} value={layout.line_height} onChange={event => patchLayout({ line_height: Number(event.target.value) })} /></label>
          <label>板块间距<input type="number" min={0} max={48} step={1} value={layout.section_gap} onChange={event => patchLayout({ section_gap: Number(event.target.value) })} /></label>
          <label>分栏<select value={layout.columns} onChange={event => patchLayout({ columns: Number(event.target.value) })}><option value={1}>单栏</option><option value={2}>双栏</option></select></label>
          <label>页数上限<input type="number" min={1} max={5} step={1} value={layout.page_limit} onChange={event => patchLayout({ page_limit: Number(event.target.value) })} /></label>
          <label className="rs-layout-photo"><span>照片</span><input type="checkbox" checked={layout.photo_enabled} onChange={event => patchLayout({ photo_enabled: event.target.checked })} /></label>
        </div><div className="rs-layout-order"><span>栏目顺序</span><ul className="layout-order-list">{layout.section_order.map((kind, index) => <li key={kind} className="layout-order-item"><span>{sectionLabel(kind)}</span><span><button type="button" aria-label={`上移 ${sectionLabel(kind)}`} disabled={busy || index === 0} onClick={() => patchLayout({ section_order: moveSection(layout.section_order, kind, -1) })}>↑</button><button type="button" aria-label={`下移 ${sectionLabel(kind)}`} disabled={busy || index === layout.section_order.length - 1} onClick={() => patchLayout({ section_order: moveSection(layout.section_order, kind, 1) })}>↓</button></span></li>)}</ul></div></div>
        <div className="rs-export"><h3>生成投递版</h3><p>{preview?.checks.filter(item => item.level === "block").length ? `还有 ${preview.checks.filter(item => item.level === "block").length} 项阻塞事实需要核对。` : "确认当前修订版后，可下载可选中文字的真实 PDF。"}</p><button type="button" onClick={() => void confirm()} disabled={busy || rendering || Boolean(preview?.checks.some(item => item.level === "block"))}>确认当前修订版</button><button type="button" className="rs-download" onClick={() => void download()} disabled={!canDownload}>下载 PDF ↗</button><button type="button" className="rs-secondary" onClick={() => void overwriteResume()} disabled={!canDownload}>用这份简历覆盖岗位简历</button><Link className="rs-next-interview" href={`/missions/${missionId}/interview`}>生成完成后，进入模拟面试 →</Link><div className="rs-export-text"><p>文本存档（不含照片，不依赖排版环境）</p>{(["markdown", "txt", "json"] as const).map(format => <button key={format} type="button" className="rs-secondary" onClick={() => void downloadText(format)}>{format === "markdown" ? "Markdown" : format === "txt" ? "纯文本" : "JSON"}</button>)}</div></div>
      </aside>
    </div>
    {gallery && <div className="rs-gallery-backdrop" role="dialog" aria-modal="true" aria-label="选择简历模板"><div className="rs-gallery"><div className="rs-gallery-header"><div><span>02 / TEMPLATE LIBRARY</span><h2>选择简历模板</h2><p>九种原创版式，各有中英版本。卡片展示服务端真实编译的完整虚构样本。</p></div><button type="button" onClick={() => setGallery(false)} aria-label="关闭模板画廊">×</button></div><div className="rs-language-tabs"><button type="button" className={galleryLanguage === "zh" ? "active" : ""} onClick={() => setGalleryLanguage("zh")}>中文模板 <b>09</b></button><button type="button" className={galleryLanguage === "en" ? "active" : ""} onClick={() => setGalleryLanguage("en")}>English templates <b>09</b></button><span>当前正文：{state.language === "zh" ? "中文" : "English"}</span></div><div className="rs-template-grid">{templates.filter(item => item.language === galleryLanguage).map((item, index) => <article key={item.id} className={`rs-template-card ${item.id === state.template_id ? "active" : ""}`}><button type="button" className="rs-template-image" onClick={() => setSampleOpen(item.id)} aria-label={`放大查看 ${item.name} 完整样本`}>{samples[item.id]?.pages[0] ? <img src={svgUrl(samples[item.id].pages[0])} alt={`${item.name} 真实样本第 1 页`} /> : <span>正在生成实际页面…</span>}</button><div className="rs-template-info"><span>{String(index + 1).padStart(2, "0")} / {item.style as string}</span><h3>{item.name}</h3><p>{samples[item.id]?.page_count || "—"} 页 · {item.language === "zh" ? "中文" : "English"}</p>{item.language === state.language ? <button type="button" disabled={item.id === state.template_id || busy} onClick={async () => { if (await mutate({ type: "set_template", template_id: item.id })) setGallery(false); }}>{item.id === state.template_id ? "正在使用" : "使用此模板"}</button> : <small>需先完成对应语言的正文，再选择模板</small>}</div></article>)}</div></div></div>}
    {gallery && galleryLanguage !== state.language && <div className="rs-language-notice" role="note">切换画廊只浏览样本，不会翻译或修改简历。完成对应语言正文后，可明确切换文档语言。<button type="button" disabled={busy} onClick={() => { if (window.confirm("语言标记只影响模板选择，不会自动翻译文字。请确认你已完成对应语言正文。")) void mutate({ type: "set_language", language: galleryLanguage }); }}>我已完成正文，切换为{galleryLanguage === "zh" ? "中文" : "English"}</button></div>}
    {sampleOpen && samples[sampleOpen] && <div className="rs-sample-backdrop" role="dialog" aria-modal="true" aria-label="模板完整样本"><div className="rs-sample-modal"><button type="button" onClick={() => setSampleOpen(null)}>关闭 ×</button><h2>{templates.find(item => item.id === sampleOpen)?.name} · 完整页面</h2>{samples[sampleOpen].pages.map((svg, index) => <img key={index} src={svgUrl(svg)} alt={`样本第 ${index + 1} 页`} />)}</div></div>}
  </main>;
}
