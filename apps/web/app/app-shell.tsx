"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";
import { useEffect, useState, type ReactNode } from "react";
import { TouTouOrb } from "./tou-tou.tsx";

type NavItem = {
  key: string;
  label: string;
  href: Route;
  icon: string;
  match: (pathname: string) => boolean;
};

const SIDEBAR_COLLAPSED_KEY = "career-os.sidebar.collapsed";

/**
 * 侧栏信息架构：主导航固定为 7 个入口（首页 / 岗位 / 简历 / 投递 / 网申 / 面试 / 设置），
 * 底层证据系统、AI 助手、网申资料等收纳到「工具」组，不再主导主导航。
 */
const JOURNEY_ITEMS: NavItem[] = [
  { key: "home", label: "首页", href: "/", icon: "overview", match: (p) => p === "/" },
  {
    key: "jobs",
    label: "岗位",
    href: "/jobs",
    icon: "jobs",
    match: (p) => p === "/jobs" || p.startsWith("/missions") || p === "/plaza",
  },
  { key: "resumes", label: "简历", href: "/resumes", icon: "resume", match: (p) => p === "/resumes" || p.startsWith("/resumes/") },
  { key: "tracker", label: "投递", href: "/tracker", icon: "tracker", match: (p) => p === "/tracker" },
  { key: "webform", label: "网申", href: "/webform", icon: "webform", match: (p) => p.startsWith("/webform") },
  {
    key: "interview-bank",
    label: "面试",
    href: "/question-bank",
    icon: "bank",
    match: (p) => p.startsWith("/question-bank") || p.startsWith("/interview-records"),
  },
  { key: "settings", label: "设置", href: "/settings", icon: "settings", match: (p) => p.startsWith("/settings") },
];

const TOOL_ITEMS: NavItem[] = [
  { key: "assistant", label: "顺顺", href: "/assistant", icon: "assistant", match: (p) => p === "/assistant" },
  // 「事实核对」(/claims) 与「证据库」职责重复，已下线；证据是唯一事实来源。
  { key: "evidence", label: "证据库", href: "/evidence-os", icon: "evidence", match: (p) => p.startsWith("/evidence-os") },
  { key: "application-profile", label: "网申资料", href: "/application-profile", icon: "profile", match: (p) => p.startsWith("/application-profile") },
  // 「上传简历」已合并进「简历中心」(/resumes)：上传、改原文、档案管理都在那里。
];

/** 线形图标（1.5 描边、圆角端点），统一几何语言。 */
const ICON_PATHS: Record<string, ReactNode> = {
  overview: (
    <>
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.6" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" />
      <rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6" />
    </>
  ),
  jobs: (
    <>
      <rect x="4" y="6" width="16" height="13" rx="2.4" />
      <path d="M8 6V5a1.8 1.8 0 0 1 1.8-1.8h4.4A1.8 1.8 0 0 1 16 5v1" />
      <path d="M4 12h16" />
    </>
  ),
  plaza: (
    <>
      <rect x="4" y="4" width="6.5" height="6.5" rx="1.6" />
      <rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6" />
      <rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6" />
      <path d="M16.5 13.5h3.5v3.5h-3.5z" />
    </>
  ),
  resume: (
    <>
      <path d="M7 3h7.2L18 6.8V19a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
      <path d="M14 3v4h4M9 12h6M9 16h4" />
    </>
  ),
  tracker: (
    <>
      <path d="M5 5v14h14" />
      <path d="M8.5 13.5l2.5-2.5 2.5 2.5 3-3.5" />
    </>
  ),
  interview: (
    <>
      <path d="M4 6h16v9.5H10l-5 4z" />
      <path d="M8 9.5h8M8 12.5h5" />
    </>
  ),
  assistant: (
    <>
      <path d="M4 6h16v10.5h-6l-4 4v-4H4z" />
      <circle cx="9" cy="11" r="1" fill="currentColor" />
      <circle cx="12" cy="11" r="1" fill="currentColor" />
      <circle cx="15" cy="11" r="1" fill="currentColor" />
    </>
  ),
  claims: (
    <>
      <path d="M12 3.5l6.5 3v5c0 3.5-2.5 6-6.5 7.5-4-1.5-6.5-4-6.5-7.5v-5z" />
      <path d="m9 12 2.2 2.2 3.8-4.2" />
    </>
  ),
  evidence: (
    <>
      <path d="M6 3.5h9L18 6.5V20a.8.8 0 0 1-.8.8H6.8A.8.8 0 0 1 6 20z" />
      <path d="M15 3.5v3h3M9 12h6M9 15.5h6" />
    </>
  ),
  upload: (
    <>
      <path d="M12 15V4" />
      <path d="m7.5 8 4.5-4.5L16.5 8" />
      <path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />
    </>
  ),
  bank: (
    <>
      <path d="M4 6.5h16" />
      <path d="M5 6.5v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-11" />
      <path d="M9.5 10.5h5M9.5 14h5" />
    </>
  ),
  profile: (
    <>
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" />
    </>
  ),
  webform: (
    <>
      <rect x="4.5" y="3.5" width="15" height="17" rx="2.2" />
      <path d="M8 8h8M8 12h8M8 16h4" />
      <path d="m15.2 16.2 1.4 1.4 2.4-2.6" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="2.6" />
      <path d="M12 3.6v2.2M12 18.2v2.2M3.6 12h2.2M18.2 12h2.2M6.1 6.1l1.6 1.6M16.3 16.3l1.6 1.6M17.9 6.1l-1.6 1.6M7.7 16.3l-1.6 1.6" />
    </>
  ),
  panelCollapse: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M9.5 5v14" />
      <path d="m14.5 10-2 2 2 2" />
    </>
  ),
  panelExpand: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M9.5 5v14" />
      <path d="m12.5 10 2 2-2 2" />
    </>
  ),
};

function NavIcon({ name }: { name: string }) {
  return (
    <svg
      className="app-nav-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name] ?? ICON_PATHS.overview}
    </svg>
  );
}

function BrandMark() {
  return (
    <svg className="app-brand-mark" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 18.5V11a2 2 0 0 1 2-2h3v9.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14 6.5V18.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <circle cx="14" cy="4.5" r="1.6" fill="currentColor" />
      <path d="M10 18.5h6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link
      className={`app-nav-item${active ? " active" : ""}`}
      href={item.href}
      aria-current={active ? "page" : undefined}
    >
      <NavIcon name={item.icon} />
      <span className="app-nav-label">{item.label}</span>
    </Link>
  );
}

function NavGroup({ title, items, pathname }: { title: string; items: NavItem[]; pathname: string }) {
  return (
    <nav className="app-nav" aria-label={title}>
      <p className="app-nav-group-title">{title}</p>
      {items.map((item) => (
        <NavLink key={item.key} item={item} active={item.match(pathname)} />
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // 收起状态初始为展开（与 SSR 一致），挂载后再读取本地记忆，避免 hydration 不匹配。
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    try {
      setCollapsed(window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "1");
    } catch {
      /* 隐私模式等场景下忽略 */
    }
  }, []);

  const toggleCollapsed = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* 忽略写入失败 */
      }
      return next;
    });
  };

  return (
    <div className={`app-shell${collapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="app-sidebar" aria-hidden={collapsed}>
        <Link className="app-brand" href="/" tabIndex={collapsed ? -1 : undefined}>
          <BrandMark />
          <span className="app-brand-name">AI Career OS</span>
        </Link>

        <div className="app-nav-columns">
          <NavGroup title="求职" items={JOURNEY_ITEMS} pathname={pathname} />
          <NavGroup title="工具" items={TOOL_ITEMS} pathname={pathname} />
        </div>

        <button
          type="button"
          className="app-sidebar-collapse"
          onClick={toggleCollapsed}
          title="收起侧栏"
          aria-label="收起侧栏"
          tabIndex={collapsed ? -1 : undefined}
        >
          <NavIcon name="panelCollapse" />
          <span className="app-nav-label">收起侧栏</span>
        </button>
      </aside>

      {collapsed ? (
        <button
          type="button"
          className="app-sidebar-expand"
          onClick={toggleCollapsed}
          title="展开侧栏"
          aria-label="展开侧栏"
        >
          <NavIcon name="panelExpand" />
        </button>
      ) : null}

      <main className="app-main">{children}</main>

      <TouTouOrb />
    </div>
  );
}
