"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  activateDataset,
  backupExportUrl,
  inspectBackup,
  readBackupSummary,
  readDatasets,
  readLocalStatus,
  restoreBackup,
  type BackupInspection,
  type DatasetItem,
  type LocalStatus,
  type RestoreResult,
} from "../settings.ts";

const COUNT_LABEL: Record<string, string> = {
  user_profiles: "简历档案",
  job_missions: "岗位",
  target_resumes: "定向简历",
  resume_studio_documents: "Studio 文档",
  job_applications: "投递记录",
  interview_records: "面试记录",
  candidate_jobs: "候选岗位",
  web_form_records: "网申填写记录",
};

export default function SettingsPage() {
  const [status, setStatus] = useState<LocalStatus | null>(null);
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [inspection, setInspection] = useState<BackupInspection | null>(null);
  const [restore, setRestore] = useState<RestoreResult | null>(null);
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const [localStatus, datasetResult, summary] = await Promise.all([readLocalStatus(), readDatasets(), readBackupSummary()]);
      setStatus(localStatus);
      setDatasets(datasetResult.datasets);
      setCounts(summary.counts);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取设置失败。");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleFile = useCallback(async (file: File) => {
    setBusy("inspect");
    setError("");
    setInfo("");
    setRestore(null);
    try {
      const result = await inspectBackup(file);
      setInspection(result);
      setPendingFile(file);
      setInfo(result.integrity_ok ? "备份完整性校验通过，可以恢复。" : "备份完整性校验未通过，已禁止恢复。");
    } catch (caught) {
      setInspection(null);
      setPendingFile(null);
      setError(caught instanceof Error ? caught.message : "解析备份失败。");
    } finally {
      setBusy("");
    }
  }, []);

  const handleRestore = useCallback(async () => {
    if (!pendingFile) return;
    setBusy("restore");
    setError("");
    try {
      const result = await restoreBackup(pendingFile, `恢复于 ${new Date().toLocaleString("zh-CN")}`);
      setRestore(result);
      setInfo(`已恢复为新数据集 ${result.dataset_id}，并切换为当前数据集。原数据集文件未被覆盖。`);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "恢复失败。");
    } finally {
      setBusy("");
    }
  }, [load, pendingFile]);

  const handleActivate = useCallback(
    async (id: string) => {
      setBusy(`activate:${id}`);
      setError("");
      try {
        await activateDataset(id);
        setInfo(`已切换到数据集 ${id}。刷新页面后生效。`);
        await load();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "切换数据集失败。");
      } finally {
        setBusy("");
      }
    },
    [load],
  );

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Settings</p>
          <h1 className="app-page-title">设置</h1>
          <p className="app-page-subtitle">
            本地优先模式、数据集与数据备份恢复。数据默认保存在本机，不需要注册账号；只有配置了模型后才会使用 AI 生成能力。
          </p>
        </div>
      </header>

      {error && (
        <p className="app-inline-error" role="alert">
          {error}
        </p>
      )}
      {info && <p className="app-muted">{info}</p>}

      <section className="app-card" aria-label="本地模式">
        <h2 className="app-card-title">本地模式</h2>
        <div className="data-table-wrap">
          <table className="data-table">
            <tbody>
              <tr>
                <td className="cell-muted">本地优先模式</td>
                <td>
                  {status?.local_mode ? <span className="app-badge filled">已启用</span> : <span className="app-badge muted">未启用</span>}
                </td>
              </tr>
              <tr>
                <td className="cell-muted">本地数据目录</td>
                <td className="cell-muted">{status?.data_dir ?? status?.default_data_dir ?? "—"}</td>
              </tr>
              <tr>
                <td className="cell-muted">当前数据集</td>
                <td className="cell-muted">{status?.active_dataset_id ?? "（主库）"}</td>
              </tr>
              <tr>
                <td className="cell-muted">模型</td>
                <td>
                  {status?.model_configured ? (
                    <span className="app-badge filled">已配置（AI 生成可用）</span>
                  ) : (
                    <span className="app-badge muted">未配置（本地业务与 PDF 导出仍可用）</span>
                  )}
                </td>
              </tr>
              <tr>
                <td className="cell-muted">监听地址</td>
                <td className="cell-muted">127.0.0.1（仅本机，不暴露公网）</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="app-card-meta">
          使用 <code>start-local.cmd</code> 启动即可启用本地优先模式；配置模型后，岗位关键词、匹配分析、简历改写等会调用云端模型，
          对应的简历事实与岗位原文会发送给模型服务商。<strong>网申敏感资料（身份证、家庭情况等）默认不发送</strong>。
        </p>
      </section>

      <section className="app-card" aria-label="当前数据">
        <h2 className="app-card-title">当前数据集记录数</h2>
        <div className="app-stat-grid">
          {Object.entries(counts).map(([key, value]) => (
            <div className="app-stat-card" key={key}>
              <span className="app-stat-label">{COUNT_LABEL[key] ?? key}</span>
              <span className="app-stat-value">{value}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="app-card" aria-label="备份导出">
        <h2 className="app-card-title">1 · 导出完整备份</h2>
        <p className="app-card-meta">
          包含数据库快照与 SHA-256 清单。<strong>不包含</strong>模型 API Key、浏览器 Cookie、密码或验证码。
        </p>
        <div className="app-row">
          <a className="app-btn primary" href={backupExportUrl("本地数据集")} download>
            导出备份（.zip）
          </a>
        </div>
      </section>

      <section className="app-card" aria-label="备份恢复">
        <h2 className="app-card-title">2 · 从备份恢复</h2>
        <p className="app-card-meta">
          恢复不会覆盖当前数据库：会先校验完整性，再把备份解包为一个<strong>新的独立数据集</strong>并切换过去。
        </p>
        <div className="app-row">
          <input
            ref={fileInput}
            type="file"
            accept=".zip"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void handleFile(file);
            }}
          />
          {busy === "inspect" ? <span className="app-muted">校验中…</span> : null}
        </div>

        {inspection ? (
          <div>
            <p className="app-card-meta">
              完整性：{inspection.integrity_ok ? <span className="app-badge filled">通过</span> : <span className="app-badge danger">未通过</span>}
              {" · "}
              创建时间：{inspection.created_at ?? "—"} · 数据集：{inspection.dataset_label ?? "—"} · 大小：
              {(inspection.size_bytes / 1024).toFixed(0)} KB
            </p>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>文件</th>
                    <th>声明大小</th>
                    <th>实际大小</th>
                    <th>SHA-256</th>
                  </tr>
                </thead>
                <tbody>
                  {inspection.files.map((file) => (
                    <tr key={file.path}>
                      <td>{file.path}</td>
                      <td className="cell-muted">{file.declared_size}</td>
                      <td className="cell-muted">{file.actual_size}</td>
                      <td>
                        {file.sha256_ok ? <span className="app-badge filled">匹配</span> : <span className="app-badge danger">不匹配</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="app-row" style={{ marginTop: "0.9rem" }}>
              <button
                type="button"
                className="app-btn primary"
                disabled={!inspection.integrity_ok || busy === "restore"}
                onClick={() => void handleRestore()}
              >
                {busy === "restore" ? "恢复中…" : "恢复为新数据集"}
              </button>
            </div>
          </div>
        ) : null}

        {restore ? (
          <p className="app-card-meta">
            已恢复：<strong>{restore.label}</strong>（{restore.dataset_id}），原数据集：{restore.previous_dataset_id ?? "无"}。
          </p>
        ) : null}
      </section>

      <section className="app-card" aria-label="数据集列表">
        <h2 className="app-card-title">本地数据集</h2>
        {datasets.length === 0 ? (
          <p className="app-empty">当前不是本地数据集模式，或还没有数据集。用 start-local.cmd 启动后可在这里看到。</p>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>来源</th>
                  <th>创建时间</th>
                  <th>大小</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      {dataset.label}
                      {dataset.active ? <span className="app-badge filled" style={{ marginLeft: "0.5rem" }}>当前</span> : null}
                    </td>
                    <td className="cell-muted">{dataset.source}</td>
                    <td className="cell-muted">{dataset.created_at ? new Date(dataset.created_at).toLocaleString("zh-CN") : "—"}</td>
                    <td className="cell-muted">{(dataset.size_bytes / 1024).toFixed(0)} KB</td>
                    <td>
                      <button
                        type="button"
                        className="app-btn subtle"
                        disabled={dataset.active || busy === `activate:${dataset.id}`}
                        onClick={() => void handleActivate(dataset.id)}
                      >
                        切换到此数据集
                      </button>
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
