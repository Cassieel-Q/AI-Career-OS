import assert from "node:assert/strict";
import test from "node:test";

import {
  dedupeProfileOptions,
  formatProfileOptionLabel,
  listProfileLabelOptions,
  PROFILE_LABELS_STORAGE_KEY,
  removeProfileLabel,
  upsertProfileLabel,
} from "../app/profile-label.ts";

function installMemoryStorage() {
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
  (globalThis as { window?: { localStorage: Storage } }).window = { localStorage };
  return store;
}

test("dedupeProfileOptions keeps first row per profile_id", () => {
  const rows = [
    { profileId: "a", label: "潘佳琪-简历" },
    { profileId: "a", label: "潘佳琪-简历-dup" },
    { profileId: "b", label: "个人简历" },
  ];
  const out = dedupeProfileOptions(rows);
  assert.equal(out.length, 2);
  assert.equal(out[0]?.label, "潘佳琪-简历");
  assert.equal(out[1]?.profileId, "b");
});

test("formatProfileOptionLabel shows name/time/origin/master/mission without UUID", () => {
  const text = formatProfileOptionLabel(
    {
      label: "潘佳琪-简历",
      updatedAt: "2026-09-24T09:16:00.000Z",
      origin: "mission_local",
      isMissionLocal: true,
      isMaster: false,
    },
    { profileId: "e0e40271-25ec-4d6a-8219-da206be34512", currentMissionBoundId: "e0e40271-25ec-4d6a-8219-da206be34512" },
  );
  assert.match(text, /潘佳琪-简历/);
  assert.match(text, /Master:否/);
  assert.match(text, /当前岗位专属|岗位专属/);
  assert.equal(text.includes("e0e40271"), false);
});

test("listProfileLabelOptions dedupes by profile_id and exposes displayLabel", () => {
  const store = installMemoryStorage();
  store.clear();
  upsertProfileLabel("id-1", "潘佳琪-简历", "resume", {
    origin: "mission_local",
    isMissionLocal: true,
    isMaster: false,
  });
  upsertProfileLabel("id-1", "潘佳琪-简历", "resume", {
    origin: "mission_local",
    isMissionLocal: true,
    isMaster: false,
  });
  upsertProfileLabel("id-2", "潘佳琪-简历", "resume", {
    origin: "master",
    isMissionLocal: false,
    isMaster: true,
  });
  const options = listProfileLabelOptions();
  assert.equal(options.length, 2);
  assert.ok(options.every((item) => item.displayLabel && !item.displayLabel.includes("id-")));
  assert.ok(options.some((item) => item.isMaster));
  assert.ok(options.some((item) => item.isMissionLocal));
  assert.ok(store.get(PROFILE_LABELS_STORAGE_KEY));
});

test("removeProfileLabel deletes only the selected local profile label", () => {
  const store = installMemoryStorage();
  upsertProfileLabel("id-1", "第一份简历", "resume");
  upsertProfileLabel("id-2", "第二份简历", "resume");

  removeProfileLabel("id-1");

  const options = listProfileLabelOptions();
  assert.deepEqual(options.map((item) => item.profileId), ["id-2"]);
  assert.ok(store.get(PROFILE_LABELS_STORAGE_KEY));
});
