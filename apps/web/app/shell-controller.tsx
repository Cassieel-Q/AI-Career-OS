"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { AppShell } from "./app-shell";

/**
 * 决定当前路由是否套用全局侧栏外壳。
 * - 顶层模块页（首页/岗位广场/简历中心/求职进度/事实台账/面试记录）→ 套侧栏
 * - 单岗位 Mission 向导详情、上传简历、证据 OS、简历工作台 → 保留各自专注外壳
 */
export function ShellController({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (shouldUseShell(pathname)) {
    return <AppShell>{children}</AppShell>;
  }
  return <>{children}</>;
}

function shouldUseShell(pathname: string): boolean {
  if (pathname === "/") return true;
  if (pathname === "/missions") return true;
  if (pathname === "/resumes" || pathname.startsWith("/resumes/")) return true;
  if (pathname === "/tracker") return true;
  if (pathname === "/claims") return true;
  if (pathname.startsWith("/interview-records")) return true;
  return false;
}
