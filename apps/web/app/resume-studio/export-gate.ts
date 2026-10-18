import type { StudioCheck, StudioPreview, StudioState } from "./types.ts";

export type DeliveryGate = {
  /** 正式投递版必须处理掉的阻塞项。 */
  blocks: StudioCheck[];
  /** 草稿口径下的阻塞项（只有内容质量问题）。 */
  draftBlocks: StudioCheck[];
  /** 不阻塞任何操作，只提示投递前建议确认。 */
  warns: StudioCheck[];
  canConfirm: boolean;
  canDownloadFinal: boolean;
  /** 草稿永远可以导出，用于先自我审阅。 */
  canDownloadDraft: boolean;
};

/**
 * 投递资格门禁（指令 4.1/4.2）：
 * - 草稿：只有占位残留、空简历这类内容质量问题会拦；未核对事实只提示；
 * - 正式投递版：还要求姓名、联系方式齐备，且高风险事实已被显式核对。
 */
export function deliveryGate(state: StudioState | null, preview: StudioPreview | null): DeliveryGate {
  const draftBlocks = (preview?.checks ?? []).filter(item => item.level === "block");
  const finalChecks = preview?.final_checks ?? preview?.checks ?? [];
  const blocks = finalChecks.filter(item => item.level === "block");
  const warns = finalChecks.filter(item => item.level === "warn");
  const confirmed = Boolean(state && state.confirmed_revision === state.revision);
  return {
    blocks,
    draftBlocks,
    warns,
    canConfirm: Boolean(state) && blocks.length === 0,
    canDownloadFinal: confirmed && blocks.length === 0,
    canDownloadDraft: Boolean(state),
  };
}
