"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Route } from "next";
import type { ReactNode } from "react";

type NavItem = {
  key: string;
  label: string;
  href: Route;
  icon: string;
  match: (pathname: string) => boolean;
};

/** 侧栏主入口：按「找岗位 → 做简历 → 投递跟进 → 面试复盘」的使用顺序排列。 */
const PRIMARY_ITEMS: NavItem[] = [
  { key: "home", label: "首页", href: "/", icon: "home", match: (p) => p === "/" },
  { key: "missions", label: "岗位广场", href: "/missions", icon: "jobs", match: (p) => p === "/missions" },
  { key: "resumes", label: "简历中心", href: "/resumes", icon: "resume", match: (p) => p === "/resumes" || p.startsWith("/resumes/") },
  { key: "tracker", label: "求职进度", href: "/tracker", icon: "tracker", match: (p) => p === "/tracker" },
  { key: "claims", label: "事实台账", href: "/claims", icon: "claims", match: (p) => p === "/claims" },
  { key: "interview", label: "面试记录", href: "/interview-records", icon: "interview", match: (p) => p.startsWith("/interview-records") },
];

/** 「我的空间」：次要但常用的模块。 */
const SPACE_ITEMS: NavItem[] = [
  { key: "upload", label: "上传简历", href: "/workflow/start", icon: "upload", match: (p) => p.startsWith("/workflow") },
  { key: "evidence", label: "证据 OS", href: "/evidence-os", icon: "evidence", match: (p) => p.startsWith("/evidence-os") },
];

const ICON_PATHS: Record<string, ReactNode> = {
  home: (
    <>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5" />
    </>
  ),
  jobs: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="2.5" />
      <path d="M8 8h8M8 12h5" />
    </>
  ),
  resume: (
    <>
      <path d="M6 3h8l4 4v14H6z" />
      <path d="M14 3v4h4M9 12h6M9 16h6" />
    </>
  ),
  tracker: (
    <>
      <path d="M4 4v16h16" />
      <path d="m7 13 3-3 3 3 5-6" />
    </>
  ),
  claims: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </>
  ),
  interview: (
    <>
      <path d="M4 5h16v10H9l-5 4z" />
      <path d="M8 9h8M8 12h5" />
    </>
  ),
  upload: (
    <>
      <path d="M12 15V4" />
      <path d="m7 8 5-5 5 5" />
      <path d="M5 15v3a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-3" />
    </>
  ),
  evidence: (
    <>
      <rect x="5" y="4" width="14" height="16" rx="2" />
      <path d="M9 9h6M9 13h6" />
    </>
  ),
};

function NavIcon({ name }: { name: string }) {
  return (
    <svg className="app-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICON_PATHS[name] ?? ICON_PATHS.home}
    </svg>
  );
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <Link className={`app-nav-item${active ? " active" : ""}`} href={item.href} aria-current={active ? "page" : undefined}>
      <NavIcon name={item.icon} />
      <span className="app-nav-label">{item.label}</span>
    </Link>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <Link className="app-brand" href="/">
          <span className="app-brand-mark" aria-hidden="true">A</span>
          <span className="app-brand-name">AI Career OS</span>
        </Link>

        <nav className="app-nav" aria-label="主导航">
          {PRIMARY_ITEMS.map((item) => (
            <NavLink key={item.key} item={item} active={item.match(pathname)} />
          ))}
        </nav>

        <div className="app-space">
          <p className="app-space-title">我的空间</p>
          <nav className="app-nav" aria-label="我的空间">
            {SPACE_ITEMS.map((item) => (
              <NavLink key={item.key} item={item} active={item.match(pathname)} />
            ))}
          </nav>
        </div>
      </aside>

      <main className="app-main">{children}</main>
    </div>
  );
}
