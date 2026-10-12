/**
 * 可折叠区块的默认状态（目标四）。
 *
 * 个人资料各板块**默认展开**，点击标题折叠；多条目照常。这里把状态收敛成纯函数，
 * 便于单测「默认展开 / 点击折叠」的行为。
 */

export type SectionOpenState = Record<string, boolean>;

/** 全部默认展开。 */
export function initialSectionState(keys: string[]): SectionOpenState {
  const state: SectionOpenState = {};
  for (const key of keys) state[key] = true;
  return state;
}

export function isSectionOpen(state: SectionOpenState, key: string): boolean {
  return state[key] !== false; // 未记录时默认展开
}

/** 切换某板块的展开/折叠，返回新状态对象。 */
export function toggleSectionState(state: SectionOpenState, key: string): SectionOpenState {
  return { ...state, [key]: !isSectionOpen(state, key) };
}
