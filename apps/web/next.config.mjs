/** @type {import('next').NextConfig} */

// NEXT_DIST_DIR 允许把开发模式的产物隔离到 .next-dev：
// `next dev` 会清空并重写 distDir，如果和 production 共用 .next，
// 一次开发模式启动就会把已经构建好的 production 产物删掉（真实踩过）。
const distDir = process.env.NEXT_DIST_DIR || ".next";

const nextConfig = {
  typedRoutes: true,
  distDir,
};

export default nextConfig;
