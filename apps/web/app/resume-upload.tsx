"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { readApiPayload } from "./profile-flow.ts";
import type { Profile } from "./profile-flow.ts";
import { API_BASE_URL, workflowHref } from "./workflow-state.ts";

export function ResumeUpload() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || loading) {
      if (!file) setError("请先选择 PDF 简历。");
      return;
    }

    setLoading(true);
    setError("");
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/resumes`, { method: "POST", body });
      const profile = await readApiPayload<Profile>(response);
      router.replace(workflowHref(profile.profile_id, "profile"));
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "简历上传失败，请重试。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="start-page">
      <header className="workflow-header start-header">
        <Link className="workflow-brand" href="/workflow/start" aria-label="AI Career OS workflow start">
          <span className="workflow-brand-mark" aria-hidden="true">A</span>
          <span>AI Career OS</span>
        </Link>
      </header>
      <section className="start-content" aria-labelledby="start-title">
        <p className="eyebrow">Evidence-driven career decisions</p>
        <h1 id="start-title">从你的真实经历开始</h1>
        <p className="summary">上传简历，先确认事实，再一步步探索适合你的职业方向。</p>
        <form className="upload-panel" onSubmit={(event) => void upload(event)}>
          <label htmlFor="resume">简历 PDF</label>
          <input
            id="resume"
            type="file"
            accept="application/pdf,.pdf"
            disabled={loading}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              setError("");
            }}
          />
          {file && <p className="file-name">已选择：{file.name}</p>}
          {error && <p className="message error" role="alert">{error}</p>}
          <button type="submit" disabled={loading || !file}>
            {loading ? "正在解析简历…" : "上传并创建 Profile"}
          </button>
          {loading && <p className="profile-note" role="status">正在提取简历事实，请稍候。</p>}
        </form>
      </section>
    </main>
  );
}
