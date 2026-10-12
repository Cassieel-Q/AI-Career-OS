"use client";

import { useCallback, useEffect, useState } from "react";

import {
  APPLICATION_PROFILE_FIELDS,
  compactApplicationProfile,
  readApplicationFillFacts,
  readApplicationProfile,
  saveApplicationProfile,
  type ApplicationProfile,
} from "../application-profile.ts";
import { readCurrentProfileId } from "../career-hub.ts";

export default function ApplicationProfilePage() {
  const [profileId, setProfileId] = useState("");
  const [form, setForm] = useState<ApplicationProfile>({});
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fillPreview, setFillPreview] = useState<string>("");

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
      setForm(await readApplicationProfile(pid));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取网申资料失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleSave = useCallback(async () => {
    if (!profileId) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const updated = await saveApplicationProfile(profileId, compactApplicationProfile(form));
      setForm(updated);
      setSaved(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "保存网申资料失败。");
    } finally {
      setBusy(false);
    }
  }, [form, profileId]);

  const handlePreview = useCallback(async () => {
    if (!profileId) return;
    try {
      const facts = await readApplicationFillFacts(profileId);
      setFillPreview(JSON.stringify(facts, null, 2));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "读取网申填表事实失败。");
    }
  }, [profileId]);

  return (
    <main className="app-page">
      <header className="app-page-header">
        <div>
          <p className="app-eyebrow">Application Profile</p>
          <h1 className="app-page-title">网申资料</h1>
          <p className="app-page-subtitle">
            自动填网申表要用的信息，和简历内容分开放。简历只会用到简历本身的事实，这里的敏感字段不会被写进简历，助手默认也读不到。
          </p>
        </div>
      </header>

      {error && <p className="app-inline-error" role="alert">{error}</p>}

      {!profileId && !loading ? (
        <section className="app-card app-empty">还没有简历档案，请先上传简历。</section>
      ) : (
        <section className="app-card" aria-label="网申资料表单">
          <div className="layout-controls">
            {APPLICATION_PROFILE_FIELDS.map((field) => (
              <label key={field.key}>
                <span>
                  {field.label}
                  {field.sensitive && <em className="app-badge muted" style={{ marginLeft: "0.4rem" }}>敏感·不进简历</em>}
                </span>
                <input
                  value={(form[field.key] as string) ?? ""}
                  onChange={(event) => setForm((prev) => ({ ...prev, [field.key]: event.target.value }))}
                  placeholder={field.sensitive ? "仅用于网申填表" : ""}
                />
              </label>
            ))}
          </div>
          <div className="mission-action-row">
            <button type="button" className="app-btn primary" disabled={busy} onClick={() => void handleSave()}>
              保存
            </button>
            <button type="button" className="app-btn" disabled={busy} onClick={() => void handlePreview()}>
              预览网申填表事实
            </button>
            {saved && <span className="app-badge filled">已保存</span>}
          </div>
          {fillPreview && <pre className="batch-draft-excerpt">{fillPreview}</pre>}
        </section>
      )}
    </main>
  );
}
