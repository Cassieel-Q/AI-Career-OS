"use client";

import { useEffect } from "react";

export default function PlazaRedirect() {
  useEffect(() => {
    window.location.replace("/missions");
  }, []);
  return <main className="app-page"><div className="app-empty">正在跳转到岗位页…</div></main>;
}
