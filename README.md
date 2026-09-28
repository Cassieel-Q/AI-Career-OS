# AI Career OS

AI Career OS turns a job description and a real resume into an evidence-grounded preparation loop:

```text
JD → understand the role → rank resume experiences → rewrite with AI
  → human approval → final resume / PDF → mock interview
  → scoring and coaching → Interview Memory
```

The product is designed for AI product, technical product, and intelligent-hardware roles. It keeps the original resume as the source of truth, separates accepted wording from fact confirmation, and uses curated Nowcoder interview packs as bounded interview context.

## What is included

- AI role understanding and JD-to-experience mapping
- Resume profile confirmation and evidence-grounded rewriting
- Experience ranking: highlight, keep, weaken, or exclude
- Target-resume approval flow and PDF export
- Mock interview with persisted sessions, turns, scoring, and follow-up coaching
- Curated company interview skills in `knowledge/interview_skills/`
- Resume-writing guardrails in `knowledge/resume_skills/`
- Permanent profile deletion with dependent workflow cleanup

## Product tour

The tour below follows one real preparation loop from a pasted JD to an interview coaching plan. Each mission keeps its own resume decisions, final resume, interview questions, answers, scores, and memory.

### 1. Start from the target job / 从目标岗位开始

Paste the complete JD. The system reads the responsibilities and requirements before it touches the resume, so every later decision stays tied to the role the candidate is actually applying for.

![粘贴完整 JD 并开始分析](docs/screenshots/product-tour-01-jd-input.png)

AI identifies the company, role, seniority, location, and the job's core focus. The user can correct these fields before continuing; the saved result becomes the identity of this job mission.

![AI 识别岗位并允许用户校正](docs/screenshots/product-tour-02-role-recognition.png)

### 2. Bind the real source resume / 选择真实简历

Choose a reusable Master Resume, upload a mission-specific PDF, or paste resume text. The selected source remains the source of truth, while every optimized version stays scoped to the current mission.

![为当前岗位选择简历来源](docs/screenshots/product-tour-03-resume-source.png)

The confirmed resume is then displayed in its original section order. Education, projects, competitions, campus experience, awards, and skills remain traceable to the uploaded source.

![原始简历与 AI 优化版本并排展示](docs/screenshots/product-tour-04-resume-optimization-overview.png)

### 3. Let AI produce the first draft / AI 判断优先级并直接改写

AI compares the complete JD with the complete resume, ranks experiences within a limited page budget, and writes the strongest project bullets directly. The left column preserves the original content; the right column shows the mission-specific rewrite and a short reason for the change.

![左右双栏查看原文与岗位定向改写](docs/screenshots/product-tour-05-resume-optimization-two-column.png)

For each experience, AI supplies a default decision: highlight, keep, weaken, or exclude. Low-relevance campus roles can be omitted automatically, while project and competition experience receives deeper rewriting. Users can override any decision.

![AI 经历排序、补做项目建议与事实确认](docs/screenshots/product-tour-06-experience-ranking-fact-check.png)

Suggested portfolio projects and newly inferred facts are visually separated from confirmed experience. They do not enter the formal resume until the user confirms that the facts are true.

### 4. Confirm the final resume and export PDF / 确认最终简历并导出

Once the selected rewrites are accepted or edited, one action confirms the final resume and generates the PDF. Another action starts the mock interview from exactly this confirmed version.

![确认最终简历、生成 PDF 或进入模拟面试](docs/screenshots/product-tour-07-final-resume-actions.png)

The final resume includes only accepted or edited real experience. Suggested projects remain outside the PDF until they have actually been completed and fact-confirmed.

![最终确认版简历预览](docs/screenshots/product-tour-08-final-resume-preview.png)

### 5. Preview, answer, review, and strengthen / 预览问题、逐题作答、复盘与补强

Before answering, the user sees a question preview generated from the JD, confirmed final resume, curated Nowcoder interview packs, and interview skills. The preview covers both capability requirements and likely follow-up directions.

![根据最终简历和 JD 生成的问题预览](docs/screenshots/product-tour-09-interview-question-preview.png)

![问题预览中的岗位能力与追问方向](docs/screenshots/product-tour-10-interview-question-preview-detail.png)

Each interview starts with one focused question and a full-width answer area. Questions stay grounded in the current mission and selected resume evidence.

![围绕简历项目生成第一道问题](docs/screenshots/product-tour-11-first-question-project.png)

The same workflow adapts to a different JD: this example begins with role fit and asks the candidate to choose the most memorable experience from the resume.

![针对不同岗位生成定位与代表经历问题](docs/screenshots/product-tour-12-first-question-role-fit.png)

After every answer, AI records a score, strengths, gaps, and a reference answer, then generates the next non-duplicate question. Feedback stays visible while the next round begins.

![单题评分、参考回答与下一道追问](docs/screenshots/product-tour-13-answer-evaluation.png)

The interview closes after the configured round limit and sends the user to the session review instead of silently resetting to question one.

![完成本轮模拟面试](docs/screenshots/product-tour-14-interview-completed.png)

Interview Memory keeps the complete question-and-answer history, per-question scores, what went well, and what needs strengthening.

![面试记录、逐题回答与总体复盘](docs/screenshots/product-tour-15-interview-memory.png)

The final coaching step converts observed gaps into actions. The user can request another 3–5 factual questions or ask AI for a concrete project-improvement guide; no proof link or artificial evidence submission is required.

![AI 生成事实追问和项目补齐步骤](docs/screenshots/product-tour-16-coaching-questions.png)

The guide finishes with recommended knowledge and reusable outputs, such as a project narrative, reproducible workflow, decision record, progress tracker, and a revised interview answer.

![AI 补强指南中的学习重点与完成产出](docs/screenshots/product-tour-17-coaching-learning-output.png)

## Repository layout

```text
apps/web/                       Next.js 15 + TypeScript frontend
apps/api/                       FastAPI + SQLAlchemy backend
knowledge/interview_skills/    curated Nowcoder/company interview packs
knowledge/resume_skills/        evidence-grounded resume writing rules
docs/product/                   product definition and user-flow notes
docs/technical/                 technical specifications
docs/superpowers/               implementation plans, specs, and QA notes
docs/release/                   release manifest and publication assets
tests/                          cross-project checks
```

## Local development

### API

```powershell
cd apps/api
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API health endpoint is `http://localhost:8000/health`.

### Web

```powershell
cd apps/web
npm install
npm run dev
```

The web app is `http://localhost:3000/missions`.

## Environment

Copy `.env.example` to `.env` for local development. API keys and database URLs belong in the server environment only; never commit `.env` or personal resume data.

The backend uses `DATABASE_URL` for runtime persistence. PostgreSQL is the production target; SQLite fixtures are used for fast unit/API tests. `TEST_DATABASE_URL` must point to a separate PostgreSQL database for the integration gate.

## Curated interview intelligence

Interview packs are Markdown files with source metadata and provenance. The curated packs under `knowledge/interview_skills/curated/` were imported from the companion interview repository and include company-specific questions and focus areas. The backend projects only bounded fields such as skill name, source references, focus, and question patterns into resume, interview, and proof prompts.

To refresh the curated packs from the companion source:

```powershell
cd apps/api
python -m app.interview_skill_importer `
  --source G:\\myself\\aicareeri-interview `
  --dest ..\\..\\knowledge\\interview_skills\\curated
```

## Verification

```powershell
cd apps/web
npm run type-check
npm test

cd ..\\api
python -m pytest -q
python -m compileall -q app
```

The PostgreSQL integration suite is intentionally skipped when no dedicated `TEST_DATABASE_URL` is configured. The release manifest records the exact verification scope for the published snapshot.

## License and data

This repository contains the application source and curated skill material. Do not commit personal resumes, candidate evidence, generated database files, API credentials, or raw audit exports.
