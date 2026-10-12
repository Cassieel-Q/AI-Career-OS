import { redirect } from "next/navigation";

/**
 * 「面试」与「题库」功能重叠，已合并为「面试题库」(/question-bank)。
 * 这里保留路径做深链兼容，直接跳到面试记录分区。
 */
export default function InterviewRecordsPage() {
  redirect("/question-bank?tab=records");
}
