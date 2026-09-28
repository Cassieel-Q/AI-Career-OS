# AI Career OS final project manifest

Date: 2026-09-28

## Published source

- Source worktree: `G:\myself\ai-career-OS-v0.2-full-intelligence`
- Branch: `feature/v0.2-full-intelligence-integration`
- Source HEAD before publication copy: `ed78ef6b9`
- Final publication copy: `G:\myself\ai-career`
- GitHub target: `https://github.com/Cassieel-Q/AI-Career-OS`

## Kept in the final repository

- `apps/web` and `apps/api`
- `knowledge/interview_skills/`, including curated Nowcoder/company packs
- `knowledge/resume_skills/`
- Product, technical, task, QA, and implementation documents
- Hydration regression test and the final profile deletion/interview-intelligence tests
- Three representative UI screenshots under `docs/screenshots/`

## Excluded from publication

- `.git`, `.next`, `node_modules`, Python virtual environments, caches, and build output
- `docs/_audit/` raw audit dumps, browser traces, generated PDFs, and screenshots containing test evidence
- API/web runtime logs and temporary patch scripts
- `.env`, database files, API keys, personal resumes, and candidate evidence

## Historical directories

The v0.2 full-intelligence worktree is the final implementation source. Earlier feature worktrees are historical development snapshots. The companion interview source `G:\myself\aicareeri-interview` and the PM reference `G:\myself\AI_CAREER_OS_PM_SKILLS_WORK_MODE_v1.0_REFERENCE` are retained as references; their reusable knowledge is copied into the final repository only where appropriate.

## Verification recorded before publication

- Web TypeScript check: passed
- Web test suite: 170 passed in the source worktree before publication packaging
- Hydration regression: passed after adding `suppressHydrationWarning` to the root HTML element
- Targeted API deletion/interview-intelligence suite: 4 passed
- Python compile check: passed
- Curated interview packs: 19 files present, including Baidu
- API health endpoint: `{"status":"ok"}`

The full historical API suite still has one unrelated pre-existing mission-provider structured-output test mismatch; it is not hidden by this manifest.
