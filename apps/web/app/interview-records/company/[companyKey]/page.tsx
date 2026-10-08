import { InterviewRecordsCompany } from "../../../interview-records-company.tsx";

export default async function Page({ params }: { params: Promise<{ companyKey: string }> }) {
  const { companyKey } = await params;
  return <InterviewRecordsCompany companyKey={companyKey} />;
}
