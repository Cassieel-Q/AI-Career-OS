import assert from "node:assert/strict";
import {
  EXPORT_SECTION_LABELS,
  NON_RESUME_PHRASES,
  buildExportFileName,
  buildPreExportChecklist,
  classifyExperienceSection,
  extractHonorFromExperience,
  findNonResumePhrase,
  formatCourseworkLine,
  formatHonorLine,
  formatHonorsSection,
  normalizeSkills,
  resolveExportProfileId,
  resolveProfileName,
} from "../app/export-resume-checks.ts";

// ---------------------------------------------------------------------------
// Fixture derived from a real live job (profile 4aa3fd6e / mission 27162e45), trimmed.
// ---------------------------------------------------------------------------
const MASTER_ID = "4aa3fd6e-7ccc-439a-a8a0-ff9ac4051370";

const expCompetition1 = {
  id: "01a2e673-62fc-460d-afc4-ba105fc61514",
  title: "第十二届全国海洋航行器设计与制作大赛",
  organization: null,
  dates: "2023.08",
  description:
    "一种集成垂荡型波能转换器的半潜式海上风力机\n国家级一等奖\n主要内容：提出创新点；动手组装浮式风机模型；测试发电效率；参加国家决赛路演与答辩。",
  experience_type: "PROJECT",
};
const expCompetition3 = {
  id: "ada57094-b0db-41eb-871c-b292c1fe410d",
  title: "第五届全国大学生可再生能源优秀科技作品竞赛",
  organization: null,
  dates: "2023.03",
  description: "10 MW 驳船式浮式风机--养殖网箱多功能融合结构设计\n国家级三等奖\n主要内容：提出风机与网箱耦合，结构建模，尺寸数值计算。",
  experience_type: "PROJECT",
};
const expCompetitionOmitted = {
  id: "2f693516-6041-4d85-b4e8-78bfd4f1078e",
  title: "第五届中国海洋工程设计大赛",
  organization: null,
  dates: "2023.10",
  description: "聚酯缆系泊系统优化\n国家级三等奖\n主要内容：数值模拟与算法优化。",
  experience_type: "PROJECT",
};
const expResearch = {
  id: "5257b4cf-001b-40b8-bdd2-76dbaade7b4f",
  title: "附有垂荡板振荡水柱波能装置水动力性能的模拟研究",
  organization: null,
  dates: "2024.11 至今",
  description: "主要内容：通过模拟运算评估垂荡板与振荡水柱协同工作效果以优化装置、提升波能利用效率。",
  experience_type: "PROJECT",
};
const expStudentUnion = {
  id: "717fc16d-98bb-43a5-9b44-ae9371eebbd2",
  title: "大连理工大学建设工程学院学生会体育部副部长",
  organization: null,
  dates: "2021.9-2023.9",
  description: "组织开展“阳光杯”啦啦操比赛，招募刘长春运动员，协助学校开展乒乓球比赛。服务志愿时长120+h。",
  experience_type: "CAMPUS",
};
const expClassCommittee = {
  id: "c63bae8c-1091-46f6-8464-06bcba5c7916",
  title: "大连理工大学建土类2104 班心理委员",
  organization: null,
  dates: "2021.9-2022.9",
  description: "定期收集同学心理健康信息，参与学校培训。组织心理剧获校级二等奖。",
  experience_type: "CAMPUS",
};
const expCoursework = {
  id: "3a7df7e3-a2bf-48b2-b4fc-0cae3fe56156",
  title: "主修课程",
  organization: null,
  dates: null,
  description:
    "结构力学、海洋工程水文学、海洋环境与荷载、海岸动力与地貌学、海洋空间资源开发工程VR 和BIM 技术、海洋资源与管理、海洋可再生能源利用系统的设计",
  experience_type: "OTHER",
};
const realExperiences = [
  expCompetition1,
  expCompetition3,
  expCompetitionOmitted,
  expResearch,
  expStudentUnion,
  expClassCommittee,
  expCoursework,
];
const realSkills = [
  { name: "Revit" },
  { name: "SuperMap" },
  { name: "AutoCAD" },
  { name: "C++" },
  { name: "python" },
  { name: "matlab" },
  { name: "MS Office" },
  { name: "MS Excel" },
  { name: "Excel" },
];
const realSelections = [
  { experience_id: "3a7df7e3-a2bf-48b2-b4fc-0cae3fe56156", decision: "OMIT" },
  { experience_id: "2f693516-6041-4d85-b4e8-78bfd4f1078e", decision: "OMIT" },
  { experience_id: "5257b4cf-001b-40b8-bdd2-76dbaade7b4f", decision: "KEEP" },
  { experience_id: "01a2e673-62fc-460d-afc4-ba105fc61514", decision: "KEEP" },
  { experience_id: "717fc16d-98bb-43a5-9b44-ae9371eebbd2", decision: "OMIT" },
  { experience_id: "ada57094-b0db-41eb-871c-b292c1fe410d", decision: "KEEP_AND_HIGHLIGHT" },
];

// ---------------------------------------------------------------------------
// 1. resolveExportProfileId
// ---------------------------------------------------------------------------
{
  // Real sample: mode=master
  const r = resolveExportProfileId({
    profile_id: MASTER_ID,
    resume_source: {
      mode: "master",
      bound_at: "2026-09-26T02:55:39.753638+00:00",
      isolation: "shared_master",
      master_profile_id: MASTER_ID,
    },
  });
  assert.deepEqual(r, { profileId: MASTER_ID, source: "resume_source.master_profile_id", mode: "master", isolation: "shared_master" });

  // upload/paste copy-on-write: bound_profile_id wins over master
  const local = resolveExportProfileId({
    profile_id: MASTER_ID,
    resume_source: { mode: "upload", isolation: "mission_local", bound_profile_id: "local-1", master_profile_id: MASTER_ID },
  });
  assert.equal(local.profileId, "local-1");
  assert.equal(local.source, "resume_source.bound_profile_id");
  assert.equal(local.isolation, "mission_local");

  // legacy key resume_source.profile_id
  const legacy = resolveExportProfileId({ profile_id: MASTER_ID, resume_source: { mode: "paste", profile_id: "legacy-2" } });
  assert.equal(legacy.profileId, "legacy-2");
  assert.equal(legacy.source, "resume_source.profile_id");

  // empty / placeholder values fall through to mission.profile_id
  const fb = resolveExportProfileId({ profile_id: MASTER_ID, resume_source: { mode: "master", bound_profile_id: "", master_profile_id: null } });
  assert.equal(fb.profileId, MASTER_ID);
  assert.equal(fb.source, "mission.profile_id");
  assert.equal(resolveExportProfileId({ profile_id: MASTER_ID, resume_source: null }).source, "mission.profile_id");
  assert.equal(resolveExportProfileId({ profile_id: MASTER_ID }).mode, null);

  // nothing at all
  assert.deepEqual(resolveExportProfileId(null), { profileId: null, source: "none", mode: null, isolation: null });
  assert.equal(resolveExportProfileId({ profile_id: "UNKNOWN", resume_source: {} }).profileId, null);
}

// ---------------------------------------------------------------------------
// 2. classifyExperienceSection / honors
// ---------------------------------------------------------------------------
{
  // coursework (type OTHER) → 教育补充
  const course = classifyExperienceSection(expCoursework);
  assert.equal(course.section, "education_extra");
  assert.equal(course.label, "教育补充");
  assert.equal(course.rule, "keyword");
  assert.equal(course.classified, true);
  assert.match(formatCourseworkLine(expCoursework), /^主修课程：结构力学、海洋工程水文学/);
  assert.equal(formatCourseworkLine({ id: "x", title: "课程", description: "课程：数据结构" }), "课程：数据结构");

  // 学生会 / 班委 → 校园经历
  assert.equal(classifyExperienceSection(expStudentUnion).section, "campus");
  assert.equal(classifyExperienceSection(expStudentUnion).label, "校园经历");
  assert.equal(classifyExperienceSection(expClassCommittee).section, "campus");
  // campus entry with an award inside but no competition title → no honor
  assert.equal(classifyExperienceSection(expClassCommittee).honor, null);
  // same titles with no type → keyword campus
  assert.equal(classifyExperienceSection({ ...expStudentUnion, experience_type: "OTHER" }).section, "campus");
  assert.equal(classifyExperienceSection({ ...expClassCommittee, experience_type: null }).rule, "keyword");
  assert.equal(classifyExperienceSection({ id: "v", title: "青年志愿者协会成员", experience_type: "" }).section, "campus");

  // explicit type wins: competition-project stays 项目, surfaces honor with award level
  const comp = classifyExperienceSection(expCompetition1);
  assert.equal(comp.section, "project");
  assert.equal(comp.rule, "type");
  assert.deepEqual(comp.honor, { title: "第十二届全国海洋航行器设计与制作大赛", level: "国家级一等奖", date: "2023.08" });
  // research project without competition → no honor
  assert.equal(classifyExperienceSection(expResearch).section, "project");
  assert.equal(classifyExperienceSection(expResearch).honor, null);
  // competition without award level → no honor
  assert.equal(extractHonorFromExperience({ id: "c", title: "全国大学生数学建模竞赛", description: "参赛", experience_type: "PROJECT" }), null);

  // explicit WORK / INTERNSHIP
  assert.equal(classifyExperienceSection({ id: "w", title: "产品实习生", experience_type: "INTERNSHIP" }).section, "work");
  assert.equal(classifyExperienceSection({ id: "w2", title: "学生会主席", experience_type: "WORK" }).section, "work");

  // keyword honors for untyped entries; competition + bullets → project
  const award = classifyExperienceSection({ id: "a", title: "校级优秀学生奖学金", dates: "2023", experience_type: "OTHER" });
  assert.equal(award.section, "honors");
  assert.equal(award.honor?.title, "校级优秀学生奖学金");
  const untypedComp = { id: "uc", title: "挑战杯全国大学生课外学术科技作品竞赛", description: "省级二等奖", experience_type: "OTHER" };
  assert.equal(classifyExperienceSection(untypedComp).section, "honors");
  const compWithBullets = classifyExperienceSection(untypedComp, { bulletCount: 2 });
  assert.equal(compWithBullets.section, "project");
  assert.equal(compWithBullets.honor?.level, "省级二等奖");

  // keyword project / work
  assert.equal(classifyExperienceSection({ id: "p", title: "毕业设计：浮式风机", experience_type: "OTHER" }).section, "project");
  assert.equal(classifyExperienceSection({ id: "k", title: "某某科技有限公司", experience_type: null }).section, "work");

  // unknown stays in type default, flagged unclassified
  const unknownOther = classifyExperienceSection({ id: "u", title: "兴趣爱好", description: "跑步", experience_type: "OTHER" });
  assert.equal(unknownOther.section, "other");
  assert.equal(unknownOther.classified, false);
  assert.equal(unknownOther.rule, "default");
  const unknownEmpty = classifyExperienceSection({ id: "u2", title: "杂项", experience_type: "" });
  assert.equal(unknownEmpty.section, "work");
  assert.equal(unknownEmpty.classified, false);
  assert.equal(EXPORT_SECTION_LABELS.honors, "荣誉奖项");

  // honors section: profile.honors first, then derived; dedupe by title; OMIT skipped when selections given
  const honors = formatHonorsSection({
    honors: [
      { title: "第十二届全国海洋航行器设计与制作大赛", level: null, date: null },
      { title: "国家奖学金", level: "国家级", date: "2024" },
    ],
    experiences: realExperiences,
    selections: realSelections,
  });
  assert.equal(honors.title, "荣誉奖项");
  assert.deepEqual(honors.lines, [
    "第十二届全国海洋航行器设计与制作大赛 · 国家级一等奖（2023.08）",
    "国家奖学金 · 国家级（2024）",
    "第五届全国大学生可再生能源优秀科技作品竞赛 · 国家级三等奖（2023.03）",
  ]);
  const honorsAll = formatHonorsSection({ experiences: realExperiences });
  assert.equal(honorsAll.lines.length, 3);
  assert.ok(honorsAll.lines.some((line) => line.indexOf("第五届中国海洋工程设计大赛") === 0));
  assert.deepEqual(formatHonorsSection({ honors: [{ title: "UNKNOWN" }], experiences: [] }).lines, []);
  assert.equal(formatHonorLine({ title: "国家级一等奖 某大赛", level: "国家级一等奖" }), "国家级一等奖 某大赛");
}

// ---------------------------------------------------------------------------
// 3. normalizeSkills
// ---------------------------------------------------------------------------
{
  assert.deepEqual(normalizeSkills(realSkills), ["Revit", "SuperMap", "AutoCAD", "C++", "Python", "MATLAB", "MS Office", "MS Excel"]);
  assert.deepEqual(normalizeSkills(["Excel", "MS Excel", "microsoft excel"]), ["Excel"]);
  assert.deepEqual(normalizeSkills(["  python ", "Python", "PYTHON", "matlab", "c++", "autocad", "ms excel"]), [
    "Python",
    "MATLAB",
    "C++",
    "AutoCAD",
    "MS Excel",
  ]);
  assert.deepEqual(normalizeSkills(["", "  ", "UNKNOWN", "未知", "产品设计", "产品 设计", null, undefined]), ["产品设计"]);
  assert.deepEqual(normalizeSkills(null), []);
}

// ---------------------------------------------------------------------------
// 4. buildPreExportChecklist
// ---------------------------------------------------------------------------
{
  assert.ok(NON_RESUME_PHRASES.indexOf("体现") >= 0);
  assert.ok(NON_RESUME_PHRASES.indexOf("面试时") >= 0);
  assert.deepEqual(findNonResumePhrase("组织开展比赛，体现持续投入与组织协调能力。"), {
    phrase: "体现",
    snippet: "体现持续投入与组织协调能力",
  });
  assert.equal(findNonResumePhrase("按背景—工作—业绩展开").phrase, "背景—工作—业绩");
  assert.equal(findNonResumePhrase("面试时可准备追问").phrase, "面试时");
  assert.equal(findNonResumePhrase("完成结构建模与尺寸数值计算"), null);

  const bullets = [
    {
      id: "b-ok",
      source_experience_id: expCompetition1.id,
      suggested_text: "完成发电效率测试，并以团队形式参加国家决赛路演与答辩，最终获国家级一等奖。",
      final_text: "完成发电效率测试，并以团队形式参加国家决赛路演与答辩，最终获国家级一等奖。",
      status: "ACCEPTED",
    },
    {
      id: "b-talk",
      source_experience_id: expCompetition3.id,
      suggested_text: "原始建议",
      final_text: "组织团队完成结构建模与数值计算，体现持续投入与组织协调能力。",
      status: "EDITED",
    },
    {
      id: "b-rejected",
      source_experience_id: expResearch.id,
      final_text: "被拒绝，面试时可展开",
      status: "REJECTED",
    },
    {
      id: "b-omitted",
      source_experience_id: expCompetitionOmitted.id,
      final_text: "OMIT 经历，彰显能力",
      status: "ACCEPTED",
    },
    {
      id: "b-ghost",
      source_experience_id: "ghost-exp",
      final_text: "幽灵经历，展现能力",
      status: "ACCEPTED",
    },
  ];
  const unknownExp = { id: "unk", title: "兴趣爱好", description: "长跑", experience_type: "OTHER" };

  // teammate-confirmed profile fields absent → warn (not block)
  const list = buildPreExportChecklist({
    profile: { profile_id: MASTER_ID, skills: realSkills } as any,
    experiences: [...realExperiences, unknownExp],
    bullets,
    selections: realSelections,
  });
  const codes = list.map((item) => item.code);
  assert.ok(list.every((item) => item.level === "warn"), "no block when bullets exist");
  assert.deepEqual(codes.filter((c) => c.indexOf("missing_") === 0), ["missing_name", "missing_phone", "missing_email"]);
  assert.match(list.find((i) => i.code === "missing_name")!.message, /缺少姓名.*投递前请补充/);
  const talk = list.filter((i) => i.code === "non_resume_phrase");
  assert.equal(talk.length, 1, "only exportable, non-omitted, non-ghost bullets are scanned");
  assert.equal(talk[0].bulletId, "b-talk");
  assert.equal(talk[0].snippet, "体现持续投入与组织协调能力");
  assert.match(talk[0].message, /「体现持续投入与组织协调能力」/);
  const unclassified = list.filter((i) => i.code === "unclassified_experience");
  assert.deepEqual(unclassified.map((i) => i.experienceId), ["unk"], "coursework / campus / projects are all classified");
  assert.match(unclassified[0].message, /兴趣爱好.*其他经历/);

  // full profile → no contact warnings
  const full = buildPreExportChecklist({
    profile: { full_name: "张三", phone: "13800000000", email: "a@b.com", city: "大连" },
    experiences: [expCompetition1],
    bullets: [bullets[0]],
  });
  assert.deepEqual(full, []);
  // `name` tolerated as fallback
  assert.equal(resolveProfileName({ name: "李四" }), "李四");
  assert.equal(resolveProfileName({ full_name: "张三", name: "李四" }), "张三");
  assert.equal(resolveProfileName({ full_name: "UNKNOWN" }), "");

  // experiences default to profile.experiences
  const viaProfile = buildPreExportChecklist({
    profile: { full_name: "张三", phone: "1", email: "e", experiences: [unknownExp] },
    bullets: [{ id: "x", source_experience_id: "unk", final_text: "长跑十年", status: "ACCEPTED" }],
  });
  assert.deepEqual(viaProfile.map((i) => i.code), ["unclassified_experience"]);

  // no exportable bullets → block first
  const empty = buildPreExportChecklist({
    profile: { full_name: "张三", phone: "1", email: "e" },
    experiences: [expCompetition1],
    bullets: [
      { id: "s", source_experience_id: expCompetition1.id, suggested_text: "未确认", status: "SUGGESTED" },
      { id: "r", source_experience_id: expCompetition1.id, final_text: "拒绝", status: "REJECTED" },
      { id: "e", source_experience_id: expCompetition1.id, final_text: "  ", suggested_text: "", status: "ACCEPTED" },
    ],
  });
  assert.equal(empty.length, 1);
  assert.equal(empty[0].level, "block");
  assert.equal(empty[0].code, "no_exportable_bullets");
  assert.match(empty[0].message, /暂无已确认要点/);
  const blockFirst = buildPreExportChecklist({ profile: null, bullets: [] });
  assert.equal(blockFirst[0].level, "block");
  assert.equal(blockFirst.length, 4);
}

// ---------------------------------------------------------------------------
// 5. buildExportFileName
// ---------------------------------------------------------------------------
{
  assert.equal(buildExportFileName({ name: "张三", company: "百度", role: "AI 产品经理实习生" }), "张三-百度-AI 产品经理实习生");
  assert.equal(buildExportFileName({ name: null, company: "百度", role: "产品经理" }), "简历-百度-产品经理");
  assert.equal(buildExportFileName({ name: "张三", company: "UNKNOWN", role: "产品经理" }), "张三-产品经理");
  assert.equal(buildExportFileName({}), "简历");
  assert.equal(buildExportFileName({ name: "张三", company: 'A/B:C*D?"E<F>G|H\\I', role: "PM" }), "张三-A B C D E F G H I-PM");
  assert.equal(buildExportFileName({ name: " 张三. ", company: "百度 投递版", role: "产品经理（投递版）" }), "张三-百度-产品经理");
  assert.equal(buildExportFileName({ name: "张三", company: "百度", role: "PM", extension: ".pdf" }), "张三-百度-PM.pdf");
  assert.equal(buildExportFileName({ name: "CON" }), "简历-CON");
  const long = buildExportFileName({ name: "张三", company: "公".repeat(80), role: "PM" });
  assert.equal(long, `张三-${"公".repeat(40)}-PM`);
  assert.doesNotMatch(buildExportFileName({ name: "张三", company: "百度", role: "实习" }), /投递版|Intern|Senior/);
}

console.log("export-resume-checks.test.mts OK");
