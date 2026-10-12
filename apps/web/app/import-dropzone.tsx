"use client";

/**
 * 统一拖拽导入组件（目标六）。
 *
 * - 校验走纯逻辑 `import-dropzone.ts`（扩展名 + MIME + 文件头 + 大小四重）；
 * - 拒绝时展示**具体原因**，不静默丢弃；
 * - 拖拽事件在 `data-dropzone` 边界内 stopPropagation，不影响区块内部拖拽排序。
 */
import { useCallback, useRef, useState } from "react";
import {
  importAcceptAttribute,
  importRuleText,
  validateImportFile,
  type ImportKind,
  type ImportPurpose,
  type ImportRejection,
} from "./import-dropzone.ts";

const HEADER_BYTES = 16;

export type AcceptedImport = { file: File; kind: ImportKind };

type Props = {
  purpose: ImportPurpose;
  onAccept: (items: AcceptedImport[]) => void;
  onReject?: (items: { file: File; rejection: ImportRejection }[]) => void;
  multiple?: boolean;
  disabled?: boolean;
  hint?: string;
};

async function probe(file: File) {
  const header = new Uint8Array(await file.slice(0, HEADER_BYTES).arrayBuffer());
  return { name: file.name, type: file.type, sizeBytes: file.size, header };
}

export function ImportDropzone({ purpose, onAccept, onReject, multiple = false, disabled = false, hint }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const handleFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList);
      const accepted: AcceptedImport[] = [];
      const rejected: { file: File; rejection: ImportRejection }[] = [];
      const messages: string[] = [];
      for (const file of files) {
        const verdict = validateImportFile(purpose, await probe(file));
        if (verdict.ok) {
          accepted.push({ file, kind: verdict.kind });
        } else {
          rejected.push({ file, rejection: verdict });
          messages.push(`${file.name}：${verdict.message}`);
        }
      }
      setErrors(messages);
      if (accepted.length) onAccept(accepted);
      if (rejected.length) onReject?.(rejected);
    },
    [onAccept, onReject, purpose],
  );

  return (
    <div
      className={`import-dropzone${dragging ? " dragging" : ""}${disabled ? " disabled" : ""}`}
      data-dropzone={purpose}
      onDragEnter={(event) => {
        if (disabled) return;
        event.preventDefault();
        event.stopPropagation();
        setDragging(true);
      }}
      onDragOver={(event) => {
        if (disabled) return;
        event.preventDefault();
        event.stopPropagation();
      }}
      onDragLeave={(event) => {
        event.stopPropagation();
        setDragging(false);
      }}
      onDrop={(event) => {
        event.preventDefault();
        event.stopPropagation();
        setDragging(false);
        if (disabled) return;
        if (event.dataTransfer?.files?.length) void handleFiles(event.dataTransfer.files);
      }}
      onClick={() => {
        if (!disabled) inputRef.current?.click();
      }}
      role="button"
      tabIndex={0}
      onKeyDown={(event) => {
        if ((event.key === "Enter" || event.key === " ") && !disabled) inputRef.current?.click();
      }}
    >
      <input
        ref={inputRef}
        type="file"
        hidden
        multiple={multiple}
        accept={importAcceptAttribute(purpose)}
        disabled={disabled}
        onClick={(event) => event.stopPropagation()}
        onChange={(event) => {
          if (event.target.files?.length) void handleFiles(event.target.files);
          event.target.value = "";
        }}
      />
      <span className="import-dropzone-title">拖拽文件到此处，或点击选择</span>
      <span className="import-dropzone-hint">{hint ?? importRuleText(purpose)}</span>
      {errors.length > 0 && (
        <ul className="import-dropzone-errors" role="alert">
          {errors.map((message) => (
            <li key={message}>{message}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ImportDropzone;
