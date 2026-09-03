import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AI Career OS",
  description: "Bootstrap workspace for AI Career OS",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
