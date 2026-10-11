"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "./app-shell";

/**
 * 决定当前路由是否套用全局侧栏外壳。
 *
 * 设计原则：整个应用是「左侧工作台 + 右侧内容」的统一结构，
 * 所有页面（总览/岗位/岗位详情/简历/投递/事实核对/面试/证据库/上传流程）都套用侧栏，
 * 保证从任意页面点进岗位后侧栏始终可见、不会退回旧的向导式布局。
 *
 * 唯一例外：简历工作台（Resume Studio）是全屏三栏沉浸式编辑器，
 * 有自己独立的顶栏与四步导航，套侧栏会挤压编辑空间，因此保留独立外壳。
 */
export function ShellController({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (shouldUseShell(pathname)) {
    return <AppShell>{children}</AppShell>;
  }
  return <>{children}</>;
}

function shouldUseShell(pathname: string): boolean {
  // 沉浸式简历工作台（Studio）保留独立全屏外壳
  if (/^\/missions\/[^/]+\/resume\/studio/.test(pathname)) return false;
  return true;
}
