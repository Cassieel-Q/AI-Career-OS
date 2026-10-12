import { redirect } from "next/navigation";

/**
 * 「事实核对」(/claims) 与「证据库」(/evidence-os) 职责重复，已下线。
 * 侧栏入口早已移除，但路由本身一直还能打开——那样「已下线」只是注释里的说法。
 * 这里收敛成服务端重定向，让「证据是唯一事实来源」真正成立。
 */
export default function ClaimsPage() {
  redirect("/evidence-os");
}
