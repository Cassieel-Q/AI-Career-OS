"use client";

import type { ReactNode } from "react";

import { AppShell } from "./app-shell";

/**
 * 全站统一「左侧工作台 + 右侧内容」外壳。
 *
 * 所有页面（总览/岗位/简历/简历工作台 Studio/投递/面试题库/证据库/上传流程）
 * 都套用同一侧栏，保证任意页面之间跳转时工作台始终可见、结构一致。
 *
 * 侧栏支持一键收起/展开（见 AppShell）：收起后右侧内容占满全屏，
 * 适合简历工作台等需要沉浸式编辑空间的场景；状态会记入 localStorage。
 */
export function ShellController({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
