import assert from "node:assert/strict";
import { test } from "node:test";
import {
  extensionOf,
  importRuleText,
  sniffHeader,
  validateImportFile,
} from "../app/import-dropzone.ts";

const bytes = (text: string) => new TextEncoder().encode(text);
const pdf = () => bytes("%PDF-1.7\n");
const png = () => new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const zip = () => new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x00, 0x00]);
const html = () => bytes("<!DOCTYPE html><html><body>x</body></html>");

test("sniffHeader reads real bytes not names", () => {
  assert.equal(sniffHeader(pdf()), "pdf");
  assert.equal(sniffHeader(png()), "image");
  assert.equal(sniffHeader(zip()), "docx");
  assert.equal(sniffHeader(html()), "html");
  assert.equal(sniffHeader(new Uint8Array([0x00, 0x01])), "unknown");
});

test("accepts a valid resume PDF", () => {
  const verdict = validateImportFile("resume-pdf", { name: "resume.pdf", type: "application/pdf", sizeBytes: 1024, header: pdf() });
  assert.equal(verdict.ok, true);
  if (verdict.ok) assert.equal(verdict.kind, "pdf");
});

test("rejects wrong extension with an explicit reason", () => {
  const verdict = validateImportFile("resume-pdf", { name: "resume.txt", type: "application/pdf", sizeBytes: 1024, header: pdf() });
  assert.equal(verdict.ok, false);
  if (!verdict.ok) {
    assert.equal(verdict.reason, "extension_not_allowed");
    assert.match(verdict.message, /不支持的文件类型/);
  }
});

test("rejects wrong MIME with an explicit reason", () => {
  const verdict = validateImportFile("resume-pdf", { name: "resume.pdf", type: "text/plain", sizeBytes: 1024, header: pdf() });
  assert.equal(verdict.ok, false);
  if (!verdict.ok) assert.equal(verdict.reason, "mime_not_allowed");
});

test("rejects oversize files with an explicit reason", () => {
  const verdict = validateImportFile("resume-pdf", { name: "resume.pdf", type: "application/pdf", sizeBytes: 11 * 1024 * 1024, header: pdf() });
  assert.equal(verdict.ok, false);
  if (!verdict.ok) {
    assert.equal(verdict.reason, "size_exceeded");
    assert.match(verdict.message, /10MB/);
  }
});

test("rejects file whose real header contradicts its extension", () => {
  const verdict = validateImportFile("resume-pdf", { name: "resume.pdf", type: "application/pdf", sizeBytes: 1024, header: zip() });
  assert.equal(verdict.ok, false);
  if (!verdict.ok) {
    assert.equal(verdict.reason, "header_mismatch");
    assert.match(verdict.message, /文件头/);
  }
});

test("template HTML has a tighter 2MB limit", () => {
  const ok = validateImportFile("template-html", { name: "t.html", type: "text/html", sizeBytes: 1024, header: html() });
  assert.equal(ok.ok, true);
  const tooBig = validateImportFile("template-html", { name: "t.html", type: "text/html", sizeBytes: 3 * 1024 * 1024, header: html() });
  assert.equal(tooBig.ok, false);
  if (!tooBig.ok) assert.equal(tooBig.reason, "size_exceeded");
  assert.match(importRuleText("template-html"), /2MB/);
});

test("attachment purpose accepts image and docx", () => {
  assert.equal(validateImportFile("attachment", { name: "a.png", type: "image/png", sizeBytes: 100, header: png() }).ok, true);
  assert.equal(validateImportFile("attachment", { name: "a.docx", type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", sizeBytes: 100, header: zip() }).ok, true);
});

test("empty file is rejected, not silently dropped", () => {
  const verdict = validateImportFile("jd", { name: "jd.txt", type: "text/plain", sizeBytes: 0, header: bytes("") });
  assert.equal(verdict.ok, false);
  if (!verdict.ok) assert.equal(verdict.reason, "empty_file");
});

test("extensionOf handles dotted names", () => {
  assert.equal(extensionOf("My.Resume.FINAL.PDF"), ".pdf");
  assert.equal(extensionOf("noext"), "");
});
