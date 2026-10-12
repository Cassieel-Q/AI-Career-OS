/**
 * 统一拖拽导入（目标六）· 纯校验逻辑。
 *
 * 四重校验：扩展名 + MIME + 文件头魔数 + 大小。任一不通过都返回**具体原因**，
 * 绝不静默丢弃。组件（import-dropzone.tsx）只负责渲染与拖拽事件隔离，规则都在这里，
 * 便于单测。
 */

export type ImportPurpose = "jd" | "resume-pdf" | "resume-image" | "template-html" | "attachment";

export type FileProbe = {
  name: string;
  /** 浏览器上报的 MIME（可能为空或不准）。 */
  type?: string;
  sizeBytes: number;
  /** 文件头若干字节（用于魔数嗅探）。 */
  header?: Uint8Array | ArrayBuffer | number[];
};

export type ImportRejection = {
  ok: false;
  reason:
    | "empty_file"
    | "size_exceeded"
    | "extension_not_allowed"
    | "mime_not_allowed"
    | "header_mismatch"
    | "header_unreadable";
  message: string;
};

export type ImportAcceptance = { ok: true; kind: ImportKind; purpose: ImportPurpose };
export type ImportVerdict = ImportAcceptance | ImportRejection;

export type ImportKind = "pdf" | "docx" | "image" | "html" | "text" | "unknown";

const MB = 1024 * 1024;

type PurposeSpec = {
  label: string;
  extensions: string[];
  mimePrefixes: string[];
  kinds: ImportKind[];
  maxBytes: number;
  allowUnknownHeader?: boolean;
};

export const IMPORT_SPECS: Record<ImportPurpose, PurposeSpec> = {
  jd: {
    label: "JD 文件",
    extensions: [".txt", ".md", ".pdf", ".docx"],
    mimePrefixes: ["text/", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword", "application/octet-stream"],
    kinds: ["text", "pdf", "docx"],
    maxBytes: 10 * MB,
  },
  "resume-pdf": {
    label: "简历 PDF",
    extensions: [".pdf"],
    mimePrefixes: ["application/pdf"],
    kinds: ["pdf"],
    maxBytes: 10 * MB,
  },
  "resume-image": {
    label: "简历图片",
    extensions: [".png", ".jpg", ".jpeg", ".webp"],
    mimePrefixes: ["image/"],
    kinds: ["image"],
    maxBytes: 10 * MB,
  },
  "template-html": {
    label: "模板 HTML",
    extensions: [".html", ".htm"],
    mimePrefixes: ["text/html", "application/xhtml+xml", "text/plain", ""],
    kinds: ["html"],
    maxBytes: 2 * MB,
    allowUnknownHeader: true,
  },
  attachment: {
    label: "附件",
    extensions: [".pdf", ".docx", ".png", ".jpg", ".jpeg", ".txt", ".md"],
    mimePrefixes: ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "image/", "text/"],
    kinds: ["pdf", "docx", "image", "text"],
    maxBytes: 10 * MB,
  },
};

export function extensionOf(name: string): string {
  const match = /(\.[a-z0-9]+)$/i.exec(name.trim().toLowerCase());
  return match ? match[1] : "";
}

function toBytes(header: FileProbe["header"]): Uint8Array | null {
  if (!header) return null;
  if (header instanceof Uint8Array) return header;
  if (header instanceof ArrayBuffer) return new Uint8Array(header);
  if (Array.isArray(header)) return new Uint8Array(header);
  return null;
}

function ascii(bytes: Uint8Array, start: number, length: number): string {
  return Array.from(bytes.slice(start, start + length))
    .map((b) => String.fromCharCode(b))
    .join("");
}

/** 用文件头魔数判断真实类型（不依赖扩展名/MIME）。 */
export function sniffHeader(header: FileProbe["header"]): ImportKind | "unknown" {
  const bytes = toBytes(header);
  if (!bytes || bytes.length < 4) return "unknown";
  if (ascii(bytes, 0, 4) === "%PDF") return "pdf";
  if (bytes[0] === 0x50 && bytes[1] === 0x4b) return "docx"; // PK zip（docx 是 zip 包）
  if (bytes[0] === 0x89 && ascii(bytes, 1, 3) === "PNG") return "image";
  if (bytes[0] === 0xff && bytes[1] === 0xd8 && bytes[2] === 0xff) return "image";
  if (ascii(bytes, 0, 4) === "RIFF" && ascii(bytes, 8, 4) === "WEBP") return "image";
  const head = new TextDecoder("utf-8", { fatal: false })
    .decode(bytes.slice(0, 512))
    .replace(/^\uFEFF/, "")
    .trimStart()
    .toLowerCase();
  if (head.startsWith("<!doctype html") || head.startsWith("<html") || head.includes("<head") || head.includes("<body")) return "html";
  if (/^[\s\S]*[a-z0-9\u4e00-\u9fa5]/i.test(head)) return "text";
  return "unknown";
}

export function validateImportFile(purpose: ImportPurpose, probe: FileProbe): ImportVerdict {
  const spec = IMPORT_SPECS[purpose];
  if (probe.sizeBytes <= 0) {
    return { ok: false, reason: "empty_file", message: `${spec.label}是空文件，已忽略。` };
  }
  if (probe.sizeBytes > spec.maxBytes) {
    return {
      ok: false,
      reason: "size_exceeded",
      message: `${spec.label}超过 ${Math.round(spec.maxBytes / MB)}MB 上限（当前 ${(probe.sizeBytes / MB).toFixed(1)}MB），请压缩后重试。`,
    };
  }
  const ext = extensionOf(probe.name);
  if (!spec.extensions.includes(ext)) {
    return { ok: false, reason: "extension_not_allowed", message: `不支持的文件类型「${ext || "无扩展名"}」，${spec.label}仅支持 ${spec.extensions.join(" / ")}。` };
  }
  const mime = (probe.type || "").toLowerCase().trim();
  const mimeOk = spec.mimePrefixes.some((prefix) => (prefix === "" ? mime === "" : mime === prefix || mime.startsWith(prefix)));
  if (!mimeOk) {
    return { ok: false, reason: "mime_not_allowed", message: `文件内容类型「${probe.type || "未知"}」与${spec.label}不符，请确认后再上传。` };
  }
  const sniffed = sniffHeader(probe.header);
  const header = toBytes(probe.header);
  if (sniffed === "unknown") {
    if (spec.allowUnknownHeader && header && header.length >= 4) {
      return { ok: true, kind: "html", purpose };
    }
    return { ok: false, reason: "header_mismatch", message: `无法识别${spec.label}的真实文件类型（文件头校验未通过）。` };
  }
  const normalized = sniffed === "docx" && spec.kinds.includes("docx") ? "docx" : sniffed;
  if (!spec.kinds.includes(normalized)) {
    return { ok: false, reason: "header_mismatch", message: `文件头显示真实类型为「${normalized}」，与${spec.label}要求不符。` };
  }
  return { ok: true, kind: normalized, purpose };
}

/** 生成拖拽区展示用的规则说明。 */
export function importAcceptAttribute(purpose: ImportPurpose): string {
  return IMPORT_SPECS[purpose].extensions.join(",");
}

export function importRuleText(purpose: ImportPurpose): string {
  const spec = IMPORT_SPECS[purpose];
  return `${spec.extensions.join(" / ")}，单个不超过 ${Math.round(spec.maxBytes / MB)}MB`;
}
