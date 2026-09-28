import { WorkflowPage } from "../../../workflow-page.tsx";

export default async function MarketProfilePage({ params }: { params: Promise<{ profileId: string }> }) {
  const { profileId } = await params;
  return <WorkflowPage profileId={profileId} currentStep="market-profile" />;
}
