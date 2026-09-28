import test from "node:test";
import assert from "node:assert/strict";

import {
  listProfileLabelOptions,
  pickLabel,
  PROFILE_LABELS_STORAGE_KEY,
  readProfileLabelRegistry,
  upsertProfileLabel,
} from "../app/profile-label.ts";

test("empty localStorage can still recover a profile by id into the registry", () => {
  const g = globalThis as typeof globalThis & { window?: { localStorage: Storage } };
  const store = new Map<string, string>();
  const localStorage = {
    getItem: (key: string) => (store.has(key) ? store.get(key)! : null),
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => store.clear(),
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    get length() {
      return store.size;
    },
  } as Storage;
  g.window = { localStorage } as typeof g.window;

  store.clear();
  assert.deepEqual(listProfileLabelOptions(), []);
  assert.deepEqual(readProfileLabelRegistry(), {});

  upsertProfileLabel("prof-recover-1", pickLabel({ resumeFilename: "个人简历.pdf" }), "resume");
  const options = listProfileLabelOptions();
  assert.equal(options.length, 1);
  assert.equal(options[0]?.profileId, "prof-recover-1");
  assert.equal(options[0]?.label, "个人简历");
  assert.ok(localStorage.getItem(PROFILE_LABELS_STORAGE_KEY));

  upsertProfileLabel("prof-recover-2", pickLabel({}), "fallback");
  assert.ok(listProfileLabelOptions().some((item) => item.label === "未命名档案"));
});
