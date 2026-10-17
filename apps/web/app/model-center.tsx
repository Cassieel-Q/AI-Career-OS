"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  activateModelConfig,
  createModelConfig,
  deleteModelConfig,
  readModelStatus,
  saveAssignments,
  testModelConnection,
  updateModelConfig,
  type Capabilities,
  type ModelConfigView,
  type ModelStatus,
  type ProviderPreset,
  type TestResult,
} from "./model-config.ts";

type Draft = {
  id: string | null;
  name: string;
  provider_id: string;
  base_url: string;
  model_id: string;
  timeout_seconds: number;
  api_key: string;
};

const EMPTY_DRAFT: Draft = {
  id: null,
  name: "",
  provider_id: "deepseek",
  base_url: "",
  model_id: "",
  timeout_seconds: 60,
  api_key: "",
};

function capabilityBadges(capabilities: Capabilities) {
  const items: Array<{ label: string; ok: boolean | null | undefined }> = [
    { label: "对话", ok: capabilities.chat },
    { label: "工具调用", ok: capabilities.tools },
    { label: "结构化 JSON", ok: capabilities.json },
    { label: "流式", ok: capabilities.streaming },
  ];
  return items.map((item) => (
    <span key={item.label} className={`app-badge ${item.ok === true ? "filled" : item.ok === false ? "attention" : "muted"}`}>
      {item.label}
      {item.ok === true ? " ✓" : item.ok === false ? " ✕" : " 未测"}
    </span>
  ));
}

export default function ModelCenter() {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [advanced, setAdvanced] = useState(false);
  const [costConfirmed, setCostConfirmed] = useState(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [result, setResult] = useState<TestResult | null>(null);
  const [assignments, setAssignmentState] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    try {
      const next = await readModelStatus();
      setStatus(next);
      setAssignmentState(next.assignments ?? {});
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取模型配置失败。");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const providers: ProviderPreset[] = status?.providers ?? [];
  const preset = useMemo(
    () => providers.find((item) => item.id === draft.provider_id) ?? null,
    [providers, draft.provider_id],
  );

  const applyPreset = useCallback(
    (providerId: string) => {
      const chosen = providers.find((item) => item.id === providerId);
      setDraft((current) => ({
        ...current,
        provider_id: providerId,
        base_url: chosen?.base_url ?? current.base_url,
        model_id: chosen?.models[0] ?? current.model_id,
      }));
    },
    [providers],
  );

  const startEdit = useCallback((config: ModelConfigView) => {
    setResult(null);
    setError("");
    setInfo("");
    setDraft({
      id: config.id,
      name: config.name,
      provider_id: config.provider_id,
      base_url: config.base_url,
      model_id: config.model_id,
      timeout_seconds: config.timeout_seconds,
      api_key: "", // 留空 = 不修改密钥
    });
  }, []);

  const handleSave = useCallback(async () => {
    setBusy("save");
    setError("");
    setInfo("");
    try {
      const payload: Record<string, unknown> = {
        name: draft.name,
        provider_id: draft.provider_id,
        base_url: draft.base_url,
        model_id: draft.model_id,
        timeout_seconds: draft.timeout_seconds,
      };
      if (draft.api_key.trim()) payload.api_key = draft.api_key.trim();
      if (draft.id) {
        await updateModelConfig(draft.id, payload);
        setInfo("已保存（未填写密钥时保持原密钥不变）。");
      } else {
        await createModelConfig(payload);
        setInfo("已新增配置。默认模型切换请点「设为默认」。");
      }
      setDraft(EMPTY_DRAFT);
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存失败。");
    } finally {
      setBusy("");
    }
  }, [draft, load]);

  const handleTest = useCallback(async () => {
    if (!costConfirmed) {
      setError("请先勾选「我了解测试会产生少量费用」再测试。");
      return;
    }
    setBusy("test");
    setError("");
    setResult(null);
    try {
      const payload: Record<string, unknown> = {
        provider_id: draft.provider_id,
        base_url: draft.base_url,
        model_id: draft.model_id,
        timeout_seconds: draft.timeout_seconds,
        confirm: true,
      };
      if (draft.id) payload.config_id = draft.id;
      if (draft.api_key.trim()) payload.api_key = draft.api_key.trim();
      const testResult = await testModelConnection(payload as never);
      setResult(testResult);
      setInfo(testResult.ok ? "连接测试通过。" : "连接测试未通过，请按下方步骤排查。");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "测试失败。");
    } finally {
      setBusy("");
    }
  }, [costConfirmed, draft, load]);

  const handleTestSaved = useCallback(
    async (config: ModelConfigView) => {
      if (!costConfirmed) {
        setError("请先勾选「我了解测试会产生少量费用」再测试。");
        return;
      }
      setBusy(`test:${config.id}`);
      setError("");
      setResult(null);
      try {
        const testResult = await testModelConnection({ config_id: config.id, confirm: true });
        setResult(testResult);
        setInfo(testResult.ok ? `「${config.name}」连接测试通过。` : `「${config.name}」连接测试未通过。`);
        await load();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "测试失败。");
      } finally {
        setBusy("");
      }
    },
    [costConfirmed, load],
  );

  const handleDelete = useCallback(
    async (config: ModelConfigView) => {
      setBusy(`delete:${config.id}`);
      setError("");
      try {
        await deleteModelConfig(config.id);
        setInfo(`已删除「${config.name}」，其密钥一并失效。`);
        if (draft.id === config.id) setDraft(EMPTY_DRAFT);
        await load();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "删除失败。");
      } finally {
        setBusy("");
      }
    },
    [draft.id, load],
  );

  const handleActivate = useCallback(
    async (config: ModelConfigView) => {
      setBusy(`activate:${config.id}`);
      setError("");
      try {
        await activateModelConfig(config.id);
        setInfo(`已将「${config.name}」设为默认模型，新会话立即生效。`);
        await load();
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : "切换失败。");
      } finally {
        setBusy("");
      }
    },
    [load],
  );

  const handleAssignments = useCallback(async () => {
    setBusy("assign");
    setError("");
    try {
      await saveAssignments(assignments);
      setInfo("模块模型分配已保存。");
      await load();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存分配失败。");
    } finally {
      setBusy("");
    }
  }, [assignments, load]);

  if (!status) {
    return (
      <section className="app-card" aria-label="AI 模型">
        <h2 className="app-card-title">AI 模型</h2>
        <p className="app-empty">{error || "读取中…"}</p>
      </section>
    );
  }

  return (
    <>
      <section className="app-card" aria-label="模型状态">
        <h2 className="app-card-title">AI 模型状态</h2>
        {status.env_warning ? (
          <p className="app-inline-error" role="alert">
            {status.env_warning}
          </p>
        ) : null}
        <div className="data-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>AI 功能</th>
                <th>生效来源</th>
                <th>模型</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {status.modules.map((module) => (
                <tr key={module.key}>
                  <td>{module.label}</td>
                  <td>
                    {module.source === "user" ? (
                      <span className="app-badge filled">我的配置</span>
                    ) : module.source === "env" ? (
                      <span className="app-badge attention">.env 环境变量</span>
                    ) : module.source === "user-broken" ? (
                      <span className="app-badge danger">配置不可用</span>
                    ) : (
                      <span className="app-badge muted">未配置</span>
                    )}
                  </td>
                  <td className="cell-muted">{module.model ?? "—"}</td>
                  <td className="cell-muted">{module.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="app-card-meta">
          配置与密钥保存在 <code>{status.storage.path}</code>（不在数据库里，因此<strong>数据集备份不包含密钥</strong>）。
          {status.secret_cipher === "dpapi" ? "密钥使用 Windows DPAPI 按当前用户加密。" : null}
          {status.secret_cipher === "plain" ? "当前环境未启用系统加密（仅调试环境）。" : null}
        </p>
      </section>

      <section className="app-card" aria-label="我的模型配置">
        <h2 className="app-card-title">我的模型配置</h2>
        {status.configs.length === 0 ? (
          <p className="app-empty">还没有配置模型。未配置时你仍可管理岗位、编辑简历和导出 PDF。</p>
        ) : (
          <div className="data-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>提供商 / 模型</th>
                  <th>密钥</th>
                  <th>能力</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {status.configs.map((config) => (
                  <tr key={config.id}>
                    <td>
                      {config.name}
                      {config.is_default ? <span className="app-badge filled" style={{ marginLeft: "0.5rem" }}>默认</span> : null}
                    </td>
                    <td className="cell-muted">
                      {config.provider_label} · {config.model_id}
                      <br />
                      <span className="app-muted">{config.base_url}</span>
                    </td>
                    <td>
                      {config.key_present ? (
                        config.key_bound ? (
                          <span className="app-badge filled">已保存 {config.key_masked}</span>
                        ) : (
                          <span className="app-badge danger">与地址不匹配，需重填</span>
                        )
                      ) : (
                        <span className="app-badge muted">未保存</span>
                      )}
                    </td>
                    <td>
                      <div className="app-row" style={{ gap: "0.3rem", flexWrap: "wrap" }}>
                        {capabilityBadges(config.capabilities)}
                      </div>
                    </td>
                    <td>
                      <div className="app-row" style={{ gap: "0.4rem", flexWrap: "wrap" }}>
                        <button type="button" className="app-btn subtle" disabled={config.is_default} onClick={() => void handleActivate(config)}>
                          设为默认
                        </button>
                        <button type="button" className="app-btn subtle" onClick={() => startEdit(config)}>
                          编辑
                        </button>
                        <button
                          type="button"
                          className="app-btn subtle"
                          disabled={busy === `test:${config.id}`}
                          onClick={() => void handleTestSaved(config)}
                        >
                          {busy === `test:${config.id}` ? "测试中…" : "测试"}
                        </button>
                        <button type="button" className="app-btn subtle" disabled={busy === `delete:${config.id}`} onClick={() => void handleDelete(config)}>
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="app-card" aria-label={draft.id ? "编辑模型配置" : "新增模型配置"}>
        <h2 className="app-card-title">{draft.id ? "编辑模型配置" : "新增模型配置"}</h2>
        <p className="app-card-meta">选择提供商 → 输入 Key → 选择模型 → 测试连接 → 保存启用。模型 ID 可以随时手改。</p>

        <div className="app-field-block">
          <label className="app-field-label" htmlFor="model-provider">提供商</label>
          <select
            id="model-provider"
            className="model-input"
            value={draft.provider_id}
            onChange={(event) => applyPreset(event.target.value)}
          >
            {providers.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
          {preset?.hint ? <p className="app-card-meta">{preset.hint}</p> : null}
          {preset?.key_url ? (
            <p className="app-card-meta">
              <a href={preset.key_url} target="_blank" rel="noreferrer">去服务商获取 API Key ↗</a>
            </p>
          ) : null}
        </div>

        <div className="app-field-block">
          <label className="app-field-label" htmlFor="model-name">配置名称</label>
          <input
            id="model-name"
            className="model-input"
            value={draft.name}
            placeholder={preset?.label ?? "例如：主力模型"}
            onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
          />
        </div>

        <div className="app-field-block">
          <label className="app-field-label" htmlFor="model-key">
            API Key
            {draft.id ? "（留空表示不修改）" : ""}
          </label>
          <input
            id="model-key"
            className="model-input"
            type="password"
            autoComplete="off"
            value={draft.api_key}
            placeholder={draft.id && status.configs.find((item) => item.id === draft.id)?.key_present ? "已保存 " + (status.configs.find((item) => item.id === draft.id)?.key_masked ?? "") + "，留空不改" : (preset?.requires_key === false ? "本地模型可留空" : "sk-...")}
            onChange={(event) => setDraft((current) => ({ ...current, api_key: event.target.value }))}
          />
          <p className="app-card-meta">密钥只保存在本机（Windows 用 DPAPI 按当前用户加密），不会写入 Git、日志或备份。</p>
        </div>

        <div className="app-field-block">
          <label className="app-field-label" htmlFor="model-id">模型 ID</label>
          <input
            id="model-id"
            className="model-input"
            list="model-id-options"
            value={draft.model_id}
            placeholder="例如 deepseek-chat"
            onChange={(event) => setDraft((current) => ({ ...current, model_id: event.target.value }))}
          />
          <datalist id="model-id-options">
            {(preset?.models ?? []).map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
        </div>

        {advanced ? (
          <div className="app-field-block">
            <label className="app-field-label" htmlFor="model-base-url">Base URL（高级）</label>
            <input
              id="model-base-url"
              className="model-input"
              value={draft.base_url}
              placeholder="https://api.deepseek.com"
              onChange={(event) => setDraft((current) => ({ ...current, base_url: event.target.value }))}
            />
            <p className="app-card-meta">只允许 HTTPS 公网地址，或本机 Ollama（127.0.0.1:11434）；内网与其它本机端口会被拒绝。</p>
          </div>
        ) : (
          <p className="app-card-meta">Base URL：{draft.base_url || "（使用提供商默认）"}</p>
        )}

        {advanced ? (
          <div className="app-field-block">
            <label className="app-field-label" htmlFor="model-timeout">超时（秒，高级）</label>
            <input
              id="model-timeout"
              className="model-input"
              type="number"
              min={5}
              max={600}
              value={draft.timeout_seconds}
              onChange={(event) => setDraft((current) => ({ ...current, timeout_seconds: Number(event.target.value) }))}
            />
          </div>
        ) : null}

        <div className="app-row" style={{ marginTop: "0.5rem" }}>
          <button type="button" className="app-btn subtle" onClick={() => setAdvanced((value) => !value)}>
            {advanced ? "收起高级选项" : "高级选项"}
          </button>
        </div>

        <div className="app-check-inline" style={{ marginTop: "0.75rem" }}>
          <input
            id="cost-confirm"
            type="checkbox"
            checked={costConfirmed}
            onChange={(event) => setCostConfirmed(event.target.checked)}
          />
          <label htmlFor="cost-confirm">我了解「测试连接」会向服务商发送极少 token 的请求，可能产生很小的费用</label>
        </div>

        <div className="app-row" style={{ marginTop: "0.75rem" }}>
          <button type="button" className="app-btn" disabled={busy === "test"} onClick={() => void handleTest()}>
            {busy === "test" ? "测试中…" : "测试连接"}
          </button>
          <button type="button" className="app-btn primary" disabled={busy === "save"} onClick={() => void handleSave()}>
            {busy === "save" ? "保存中…" : draft.id ? "保存修改" : "保存并新增"}
          </button>
          {draft.id ? (
            <button type="button" className="app-btn subtle" onClick={() => setDraft(EMPTY_DRAFT)}>
              取消编辑
            </button>
          ) : null}
        </div>

        {result ? (
          <div style={{ marginTop: "1rem" }}>
            <p className="app-card-meta">
              测试结果：{result.ok ? <span className="app-badge filled">通过</span> : <span className="app-badge danger">未通过</span>}
              {" · "}
              {result.elapsed_ms} ms · {result.cost_note}
            </p>
            <div className="data-table-wrap">
              <table className="data-table">
                <tbody>
                  {result.steps.map((step) => (
                    <tr key={step.step}>
                      <td style={{ width: "8rem" }}>{step.step}</td>
                      <td style={{ width: "5rem" }}>
                        {step.ok === true ? (
                          <span className="app-badge filled">通过</span>
                        ) : step.ok === false ? (
                          <span className="app-badge danger">失败</span>
                        ) : (
                          <span className="app-badge muted">跳过</span>
                        )}
                      </td>
                      <td className="cell-muted">{step.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {result.error ? <p className="app-inline-error">{result.error.message}</p> : null}
          </div>
        ) : null}
      </section>

      <section className="app-card" aria-label="各 AI 功能使用的模型">
        <h2 className="app-card-title">高级：各 AI 功能使用的模型</h2>
        <p className="app-card-meta">默认全部跟随「默认模型」；也可以给单个功能单独指定（例如顺顺用更强的模型）。</p>
        {status.modules.map((module) => (
          <div className="app-field-block" key={module.key}>
            <label className="app-field-label" htmlFor={`assign-${module.key}`}>{module.label}</label>
            <select
              id={`assign-${module.key}`}
              className="model-input"
              value={assignments[module.key] ?? ""}
              onChange={(event) =>
                setAssignmentState((current) => {
                  const next = { ...current };
                  if (event.target.value) next[module.key] = event.target.value;
                  else delete next[module.key];
                  return next;
                })
              }
            >
              <option value="">跟随默认模型</option>
              {status.configs.map((config) => (
                <option key={config.id} value={config.id}>{config.name}（{config.model_id}）</option>
              ))}
            </select>
          </div>
        ))}
        <div className="app-row">
          <button type="button" className="app-btn primary" disabled={busy === "assign"} onClick={() => void handleAssignments()}>
            {busy === "assign" ? "保存中…" : "保存分配"}
          </button>
        </div>
      </section>

      {error ? <p className="app-inline-error" role="alert">{error}</p> : null}
      {info ? <p className="app-muted">{info}</p> : null}
    </>
  );
}
