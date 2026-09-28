import { MissionCreate } from "../../mission-create.tsx";

type Search = { profile_id?: string };

/** /missions/new — 粘贴 JD 分析入口（始终可进，不依赖已有 mission）。 */
export default async function NewMissionPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const resolved = await Promise.resolve(searchParams);
  const profileId = resolved?.profile_id?.trim() || "";
  return <MissionCreate profileId={profileId || undefined} />;
}
