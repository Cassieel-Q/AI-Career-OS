/**
 * Next.js 的 searchParams 对重复 key（`?a=1&a=2`）给的是 `string[]`，
 * 不是 `string`。直接 `.trim()` 会抛 “...trim is not a function”，
 * 在服务端渲染阶段就是一次 500（`/missions/new?profile_id=a&profile_id=b` 实测过）。
 * 统一在这里收敛成单个字符串。
 */
export type SearchParamValue = string | string[] | undefined;

/** 取第一个值并 trim；缺失或空值返回 ""。 */
export function readSearchParam(value: SearchParamValue): string {
  if (Array.isArray(value)) return (value[0] ?? "").trim();
  return (value ?? "").trim();
}
