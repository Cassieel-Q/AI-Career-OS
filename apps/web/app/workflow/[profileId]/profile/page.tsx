import { redirect } from "next/navigation";

/** Abandoned multi-step「职业规划流程」Profile entry — seal to Mission home. */
export default async function ProfileWorkflowPage({
  params,
}: {
  params: Promise<{ profileId: string }>;
}) {
  await params;
  redirect("/missions");
}
