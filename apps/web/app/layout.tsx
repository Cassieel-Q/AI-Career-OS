import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Career OS",
  description: "Review and confirm an evidence-led career profile",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
