"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { readCurrentProfileId } from "../career-hub.ts";
import {
  WEBFORM_TEST_PAGE,
  fillWebform,
  openWebformUrl,
  readWebformPlan,
  readWebformRecords,
  readWebformStatus,
  startWebformSession,
  type WebformFillResult,
  type WebformPlan,
  type WebformRead,
  type WebformRecord,
  type WebformStatus,
} from "../webform.ts";

const SUPPORT_LABEL: Record<string, string> = {
  FULL: "完整支持",
  PARTIAL: "部分支持",
  LIMITED: "有限支持",
  UNSUPPORTED: "不支持",
  BLOCKED: "禁止填写",
};

const STATUS_LABEL: Record<string, string> = {
  READY: "可填写",
  NEEDS_CONFIRM: "待确认",
  UNSUPPORTED: "不支持",
  BLOCKED: "已拦截",
};

const STATUS_CLASS: Record<string, string> = {
  READY: "filled",
  NEEDS_CONFIRM: "attention",
  UNSUPPORTED: "muted",
  BLOCKED: "danger",
};

type Row = WebformPlan & { checked: boolean; editedValue: string };

export default function WebformPage() {
  const [profileId, setProfileId] = useState("");
  const [status, setStatus] = useState<WebformStatus | null>(null);
  const [url, setUrl] = useState("");
  const [read, setRead] = useState<WebformRead | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [result, setResult] = useState<WebformFillResult | null>(null);
  const [records, setRecords] = useState<WebformRecord[]>([]);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await readWebformStatus());
    } catch (caught) {
      setStatus({ available: false, bridge_url: "", error: caught instanceof Error ? caught.message : "无法连接后端" });
    }
  }, []);

  const refreshRecords = useCallback(async (pid: string) => {
    if (!pid) return;
    try {
      setRecords((await readWebformRecords(pid)).records);
    } catch {
      /* 历史读取失败不阻塞主流程 */
    }
  }, []);

  useEffect(() => {
    const pid = readCurrentProfileId();
    setProfileId(pid);
    void refreshStatus();
    void refreshRecords(pid);
  }, [refreshStatus, refreshRecords]);

  const summary = read?.summary;

  const toRows = useCallback((data: WebformRead): Row[] => {
    return data.plans.map((plan) => ({
      ...plan,
      checked: plan.status === "READY",
      editedValue: plan.value,
    }));
  }, []);

  const handleStart = useCallback(
    async (target?: string) => {
      setBusy("session");
      setError("");
      setInfo("");
      try {
        const opened = target ? await openWebformUrl(target) : await startWebformSession();
        setInfo(`受控浏览器已就绪：${opened.pageUrl || "空白页"}`);
        await refreshStatus();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "启动受控浏览器失败。");
      } finally {
        setBusy("");
      }
    },
    [refreshStatus],
  );

  const handleRead = useCallback(async () => {
    if (!profileId) {
      setError("还没有简历档案，请先上传简历。");
      return;
    }
    setBusy("read");
    setError("");
    setResult(null);
    try {
      const data = await readWebformPlan(profileId);
      setRead(data);
      setRows(toRows(data));
      setInfo(`已读取表单：共 ${data.summary.total} 个字段。`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取表单失败。");
    } finally {
      setBusy("");
    }
  }, [profileId, toRows]);

  const handleFill = useCallback(async () => {
    if (!read) return;
    const selected = rows.filter((row) => row.checked && row.status !== "BLOCKED" && row.editedValue.trim().length > 0);
    if (!selected.length) {
      setError("没有勾选任何可填写的字段。");
      return;
    }
    setBusy("fill");
    setError("");
    try {
      const data = await fillWebform(profileId, {
        page_url: read.page_url,
        page_title: read.page_title,
        assignments: selected.map((row) => ({
          index: row.index,
          selector: row.selector,
          control: row.control,
          label: row.label,
          value: row.editedValue,
        })),
      });
      setResult(data);
      setInfo("填写完成，但**未提交**。请回到浏览器核对后自行提交。");
      await refreshRecords(profileId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "填写失败。");
    } finally {
      setBusy("");
    }
  }, [profileId, read, refreshRecords, rows]);

  const counts = useMemo(() => {
    const map = { selectable: 0, checked: 0 };
    for (const row of rows) {
      if (row.status === "READY" || row.status === "NEEDS_CONFIRM") map.selectable += 1;
      if (row.checked && row.status !== "BLOCKED") map.checked += 1;
    }
    return map;
  }, [rows]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Web Form Autofill</p>
          <h1 className="app-page-title">网申填表</h1>
          <p className="app-page-subtitle">
            在你自己启动的本地浏览器里读取网申表单，用已确认的资料匹配字段；逐条预览、勾选后再填写。
            <strong> 系统永不点击最终提交按钮</strong>，不处理密码与验证码，也不会记录任何凭据。
          </p>
        </div>
      </header>

      {error && (
        <p className="app-inline-error" role="alert">
          {error}
        </p>
      )}
      {info && <p className="app-muted">{info}</p>}

      <section className="app-card" aria-label="受控浏览器">
        <h2 className="app-card-title">1 · 启动受控浏览器</h2>
        <p className="app-card-meta">
          需要先在项目根目录运行 <code>start-browser-bridge.cmd</code>。
          {status?.available ? (
            <>
              {" "}
              当前状态：<span className="app-badge filled">已连接</span>
              {status.session ? <span className="app-badge muted">会话已开启</span> : <span className="app-badge muted">尚无会话</span>}
            </>
          ) : (
            <>
              {" "}
              当前状态：<span className="app-badge danger">未连接</span>
              {status?.error ? <span className="app-muted">（{status.error}）</span> : null}
            </>
          )}
        </p>
        <div className="app-row">
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="要打开的网申页面地址，留空则开启空白页"
          />
          <button type="button" className="app-btn" disabled={busy === "session"} onClick={() => void handleStart(url || undefined)}>
            {busy === "session" ? "启动中…" : "启动 / 打开页面"}
          </button>
          <button type="button" className="app-btn subtle" disabled={busy === "session"} onClick={() => void handleStart(WEBFORM_TEST_PAGE)}>
            用本地测试表单试用
          </button>
          <button type="button" className="app-btn subtle" onClick={() => void refreshStatus()}>
            刷新状态
          </button>
        </div>
      </section>

      <section className="app-card" aria-label="读取与匹配">
        <h2 className="app-card-title">2 · 读取表单并匹配资料</h2>
        <p className="app-card-meta">
          只会把下列已保存资料用于匹配；敏感字段仅在你确认填写时才会写入页面。
        </p>
        <div className="app-row">
          <button type="button" className="app-btn primary" disabled={busy === "read"} onClick={() => void handleRead()}>
            {busy === "read" ? "读取中…" : "读取当前页面表单"}
          </button>
          {read ? (
            <span className="app-muted">
              共 {read.summary.total} 个字段：可填写 {read.summary.ready}、待确认 {read.summary.needs_confirm}、不支持{" "}
              {read.summary.unsupported}、已拦截 {read.summary.blocked}
            </span>
          ) : null}
        </div>
        {read && read.sensitive_keys_used.length > 0 ? (
          <p className="app-card-meta">
            本次匹配用到的<strong>敏感字段</strong>：{read.sensitive_keys_used.join("、")}（与你手动填写的效果一致，仅写入当前页面）
          </p>
        ) : null}
      </section>

      {rows.length > 0 ? (
        <section className="app-card" aria-label="填写预览">
          <h2 className="app-card-title">3 · 逐条预览</h2>
          <p className="app-card-meta">
            可填 {counts.selectable} 项，已勾选 {counts.checked} 项。可逐条编辑取值或取消勾选；「已拦截」的项目永远不可勾选。
          </p>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th> </th>
                  <th>字段</th>
                  <th>控件</th>
                  <th>支持程度</th>
                  <th>匹配来源</th>
                  <th>将写入的值</th>
                  <th>状态 / 原因</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, position) => (
                  <tr key={`${row.index}-${row.selector}`}>
                    <td>
                      <input
                        type="checkbox"
                        checked={row.checked}
                        disabled={row.status === "BLOCKED" || row.status === "UNSUPPORTED"}
                        onChange={(event) =>
                          setRows((prev) =>
                            prev.map((item, idx) => (idx === position ? { ...item, checked: event.target.checked } : item)),
                          )
                        }
                        aria-label={`选择填写 ${row.label}`}
                      />
                    </td>
                    <td>{row.label || "（无标签）"}</td>
                    <td className="cell-muted">{row.control}</td>
                    <td>{SUPPORT_LABEL[row.support] ?? row.support}</td>
                    <td className="cell-muted">{row.match_label ?? "—"}</td>
                    <td>
                      <input
                        value={row.editedValue}
                        disabled={row.status === "BLOCKED" || row.status === "UNSUPPORTED"}
                        placeholder={row.status === "NEEDS_CONFIRM" ? "请补全后再填写" : ""}
                        onChange={(event) =>
                          setRows((prev) =>
                            prev.map((item, idx) => (idx === position ? { ...item, editedValue: event.target.value } : item)),
                          )
                        }
                        aria-label={`${row.label} 的取值`}
                      />
                    </td>
                    <td>
                      <span className={`app-badge ${STATUS_CLASS[row.status] ?? ""}`}>{STATUS_LABEL[row.status] ?? row.status}</span>
                      <span className="cell-muted"> {row.reason}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="app-row" style={{ marginTop: "0.9rem" }}>
            <button type="button" className="app-btn primary" disabled={busy === "fill"} onClick={() => void handleFill()}>
              {busy === "fill" ? "填写中…" : `执行填写（${counts.checked} 项）`}
            </button>
            <span className="app-muted">只填写，不提交。</span>
          </div>
        </section>
      ) : null}

      {result ? (
        <section className="app-card" aria-label="填写结果">
          <h2 className="app-card-title">4 · 填写结果</h2>
          <p className="app-card-meta">
            成功 {result.summary.filled} · 失败 {result.summary.failed} · 跳过 {result.summary.skipped} ·{" "}
            <strong>已提交：否</strong>
          </p>
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>字段</th>
                  <th>结果</th>
                  <th>原因</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((item, idx) => (
                  <tr key={`${item.selector}-${idx}`}>
                    <td>{item.label || item.selector}</td>
                    <td>
                      <span className={`app-badge ${item.ok ? "filled" : "danger"}`}>{item.ok ? "成功" : "失败"}</span>
                    </td>
                    <td className="cell-muted">{item.reason || "—"}</td>
                  </tr>
                ))}
                {result.rejected.map((item, idx) => (
                  <tr key={`rejected-${idx}`}>
                    <td>{item.label || item.control}</td>
                    <td>
                      <span className="app-badge attention">跳过</span>
                    </td>
                    <td className="cell-muted">{item.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <section className="app-card" aria-label="填写历史">
        <h2 className="app-card-title">填写历史</h2>
        {records.length === 0 ? (
          <p className="app-empty">还没有填写记录。</p>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>页面</th>
                  <th>状态</th>
                  <th>结果</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    <td className="cell-muted">{record.created_at ? new Date(record.created_at).toLocaleString("zh-CN") : "—"}</td>
                    <td className="cell-title-link">{record.page_title || record.page_url}</td>
                    <td>
                      <span className={`app-badge ${record.status === "FILLED" ? "filled" : "danger"}`}>{record.status}</span>
                    </td>
                    <td className="cell-muted">
                      成功 {record.summary?.filled ?? 0} · 跳过 {record.summary?.skipped ?? 0}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="app-card-meta">仅记录字段名与结果，不记录密码或验证码。</p>
      </section>

      {summary ? (
        <section className="app-stat-grid" aria-label="本次表单统计">
          <div className="app-stat-card">
            <span className="app-stat-label">字段总数</span>
            <span className="app-stat-value">{summary.total}</span>
          </div>
          <div className="app-stat-card">
            <span className="app-stat-label">可填写</span>
            <span className="app-stat-value">{summary.ready}</span>
          </div>
          <div className="app-stat-card">
            <span className="app-stat-label">待确认</span>
            <span className="app-stat-value">{summary.needs_confirm}</span>
          </div>
          <div className="app-stat-card">
            <span className="app-stat-label">不支持 / 拦截</span>
            <span className="app-stat-value">
              {summary.unsupported} / {summary.blocked}
            </span>
          </div>
        </section>
      ) : null}
    </main>
  );
}
