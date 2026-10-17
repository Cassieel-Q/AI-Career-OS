# 测试结果

分支：`feature/boss-local-app` · 记录时间：2026-10-17（持续更新）

## 一、后端 pytest

| 测试文件 | 结果 | 说明 |
| --- | --- | --- |
| `tests/test_manual_import.py` | **23 / 23 通过** | M2 新增：解析（BOSS 版式 / 标签版式 / 缺失字段 / 注入告警 / HTML 剥离 / 来源字段优先）、保存去重（重复不新增、同公司不同岗位、同岗位不同城市、JD 变化差异提示、用户编辑保留、凭据内容拒绝）、扩展鉴权（未配对 409、配对码一次性、错令牌 401、外来 Origin 403、超大请求体、令牌不外泄）；本轮补 2 项：岗位名「招聘」前缀剥离、来源如实记录（不虚标 BOSS） |
| `tests/test_boss_kit.py` | **8 / 8 通过** | M3 新增：原岗位链接暴露、话术生成只引用真实字段、编辑后保存、标记已投递、已绑定简历不被替换、跟进提醒默认标题、404、候选导入把 source_url 带进正式岗位 |
| 全量 `pytest tests` | 见下 | 与基线对比 |

### 全量结果对比

| 轮次 | 通过 | 失败 | 跳过 |
| --- | --- | --- | --- |
| 基线（进入本分支前） | 887 左右 | 7 | — |
| 本轮（含新增 23+8 项） | **916** | 7 | 5 |

- 唯一的「新增失败项」`test_bind_resume_records_version_revision_and_pdf_snapshot`
  在 CPU 空闲后复跑**通过**（原报 Typst 排版超时，是 `next build` 抢占 CPU 导致）。
- 当前 7 项失败，已逐个在基线提交 `c3268ac` 上单独复跑验证，**全部同样失败** → 既有问题，与本次改动无关。
  失败清单：`test_claim_provider_normalizes_partial_claim_schema`、
  `test_gap_analysis_uses_confirmed_profile_and_allowed_states`、
  `test_market_profile_exposes_grounded_capability_clusters_without_discarding_atomics`、
  `test_priority_algorithm_is_stable_and_caps_now`、
  `test_repeated_education_merge_preserves_optional_fields_and_courses`、
  `test_four_week_roadmap_is_persisted_with_actionable_tasks`、
  `test_claim_analysis_fingerprint_requires_regeneration_after_profile_change`。

## 二、TypeScript 类型检查

```
cd apps/web && node node_modules/typescript/bin/tsc --noEmit
```

- 第一轮：**2 处类型错误**（均在新写的 `app/jobs/import/page.tsx`）
  1. `employment_type: string` 赋给 `JobDraft["employment_type"]` 联合类型；
  2. `hardWarnings` 被推断成字面量数组，导致 `includes(code: string)` 报错。
- 修复后：**0 错误**。

## 三、Production 构建

| 轮次 | 结果 |
| --- | --- |
| 1（G 盘原地） | 失败：`Error: [safe-delete] 操作失败: spawnSync genie-trash ETIMEDOUT`（宿主环境在 next 清理 `.next` 时拦截 `fs.unlink`）+ 上面那 2 个 TS 错误 |
| 2（G 盘原地，修完 TS） | 仍失败于同一 unlink 拦截 |
| 3（D 盘 NTFS 隔离 `D:\ai-career-web-build\web`） | **EXIT=0** |
| 4（含导入页 `#f-*` 字段 id 修复，重建） | **EXIT=0**，BUILD_ID `Zipv3ZZCpQJZjJCqsgjg9`，已复制回 `G:\myself\ai-career\apps\web\.next` 并实机启动验证（8100/3000 均 200） |

> 说明：G 盘是 exFAT 移动硬盘。构建脚本 `build-web.ps1` 内置
> 「G 盘失败 → 复制到 `D:\ai-career-web-build\web` → 在 NTFS 上构建 → 把 `.next` 复制回 G」的兜底。

## 四、浏览器 E2E

| 脚本 | 覆盖 | 结果 |
| --- | --- | --- |
| `apps/web/scripts/e2e-boss-local-app.cjs` | 主流程（导入 → 匹配 → 话术 → 投递 → 快照 → Studio → PDF → 去重 → 无 JS 报错） | 首轮 **12/16**（4 项已定位修完），修复后 **18/18 通过** |
| `apps/web/scripts/e2e-extension-safety.cjs` | 扩展 9 步（抽取正确、不读密码/Cookie、非岗位页、结构变化降级、未配对拒绝、令牌/Origin、重复导入、外来网页拦截、服务不可用） | **9/9 通过** |

## 五、一键启动验收

`scripts/local-app/test-launcher.ps1`：stop → start → start → stop → start，
全程核对「8000 上的其他项目 PID 不变」「第二次 start 不产生第二套进程」
「重启后当前数据集不变」「会记录 Edge --app 独立窗口调用」。

**结果：17/17 通过**。
（Edge 复用既有实例时 `--app` 进程会立即退出，进程列表查不到属正常；
因此改为把浏览器调用事实写进 `<数据目录>/runtime/local-app-state.json` 的 `browser` 字段供事后核对。）
