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

### 1. Start from a job mission

![岗位准备工作台](docs/screenshots/mission-home.png)

Create a mission from a JD or select an existing resume profile. Each mission keeps its target company, role, resume decisions, interview preparation, and history together.

### 2. Understand the target role

![岗位理解](docs/screenshots/mission-shell.png)

The role page explains what the JD is asking for before resume decisions are made.

### 3. Keep resume profiles organized

![简历档案选择](docs/screenshots/mission-home-profile-picker.png)

Profiles can be selected, recovered by ID, or permanently deleted. Deletion removes the profile and its associated target jobs, missions, resumes, interview sessions, proof records, and local picker entry.

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
