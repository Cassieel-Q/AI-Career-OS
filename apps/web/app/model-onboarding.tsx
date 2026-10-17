"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { readModelStatus, type ModelStatus } from "./model-config.ts";

const SKIP_KEY = "ai-career:onboarding:model-skipped";

/**
 * 首用引导：导入简历 → 配置模型（可跳过）→ 导入岗位 → 得到第一份岗位版简历。
 * 只在本机 localStorage 记一个「是否跳过」的布尔值，**不保存任何密钥**。
 */
export default function ModelOnboarding({
  hasProfile,
  missionCount,
  resumeCount,
}: {
  hasProfile: boolean;
  missionCount: number;
  resumeCount: number;
}) {
  const [status, setStatus] = useState<ModelStatus | null>(null);
  const [skipped, setSkipped] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await readModelStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  useEffect(() => {
    void load();
    try {
      setSkipped(window.localStorage.getItem(SKIP_KEY) === "1");
    } catch {
      setSkipped(false);
    }
  }, [load]);

  const configured = Boolean(status?.configured);
  // 全部完成 → 不再显示引导
  if (configured && hasProfile && missionCount > 0 && resumeCount > 0) return null;

  const steps: Array<{ title: string; done: boolean; href: string; cta: string; hint?: string }> = [
    {
      title: "导入简历",
      done: hasProfile,
      href: "/resumes",
      cta: "去上传",
      hint: "一次上传，之后所有岗位共用这一份事实底稿。",
    },
    {
      title: "配置 AI 模型",
      done: configured,
      href: "/settings",
      cta: configured ? "已配置" : "去配置",
      hint: "输入你自己的 API Key；也可以跳过，先体验本地功能。",
    },
    {
      title: "导入岗位",
      done: missionCount > 0,
      href: "/missions/new",
      cta: "新建岗位",
      hint: "粘贴 JD，或从 BOSS 导入。",
    },
    {
      title: "得到第一份岗位版简历",
      done: resumeCount > 0,
      href: "/missions",
      cta: "查看岗位",
      hint: "按 JD 定向改写，逐条标注证据来源。",
    },
  ];

  const current = steps.findIndex((step) => !step.done);

  return (
    <section className="app-card" aria-label="首次使用引导">
      <h2 className="app-card-title">开始使用</h2>
      <ol className="app-list" style={{ marginBottom: "0.75rem" }}>
        {steps.map((step, index) => (
          <li key={step.title} style={{ opacity: step.done ? 0.55 : 1 }}>
            <span className="app-badge filled">{index + 1}</span>{" "}
            <strong>{step.title}</strong>
            {step.done ? <span className="app-badge filled" style={{ marginLeft: "0.5rem" }}>已完成</span> : null}
            {step.hint ? <span className="app-card-meta">{step.hint}</span> : null}
            {!step.done && index === current ? (
              <Link className="app-btn subtle" href={step.href as never} style={{ marginLeft: "0.5rem" }}>
                {step.cta}
              </Link>
            ) : null}
          </li>
        ))}
      </ol>

      {!configured ? (
        <div className="model-onboarding">
          <p className="app-card-meta" style={{ margin: 0 }}>
            {skipped
              ? "未配置 AI 模型，你仍可以管理岗位、编辑简历和导出 PDF。配置后可使用 AI 改写和顺顺。"
              : "还没有配置 AI 模型。配置后可使用 AI 改写、JD 分析、模拟面试和顺顺；不配置也能正常使用岗位管理、简历编辑与 PDF 导出。"}
          </p>
          <div className="app-row">
            <Link className="app-btn primary" href="/settings">
              配置模型
            </Link>
            {!skipped ? (
              <button
                type="button"
                className="app-btn subtle"
                onClick={() => {
                  try {
                    window.localStorage.setItem(SKIP_KEY, "1");
                  } catch {
                    /* 隐私模式下忽略 */
                  }
                  setSkipped(true);
                }}
              >
                先跳过
              </button>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
