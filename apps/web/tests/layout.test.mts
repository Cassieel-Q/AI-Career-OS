import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

test("root html tolerates browser extension attributes during hydration", async () => {
  const root = dirname(fileURLToPath(import.meta.url));
  const source = await readFile(resolve(root, "../app/layout.tsx"), "utf8");
  assert.match(source, /<html\s+lang=\"zh-CN\"\s+suppressHydrationWarning>/);
});
