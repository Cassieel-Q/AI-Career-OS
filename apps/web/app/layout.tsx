import type { Metadata } from "next";
import "./globals.css";
import { ShellController } from "./shell-controller";

export const metadata: Metadata = {
  title: "AI Career OS",
  description: "管理目标岗位、简历版本、求职进度与模拟面试。",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;600;700&display=swap" rel="stylesheet" />
      </head>
      <body>
        <ShellController>{children}</ShellController>
      </body>
    </html>
  );
}
