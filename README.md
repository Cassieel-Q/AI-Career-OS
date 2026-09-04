# AI Career OS

AI Career OS is an evidence-led career planning product for AI and large-language-model roles.

## Repository Layout

```text
apps/
  web/       Next.js + TypeScript + Tailwind frontend
  api/       FastAPI backend
docs/
  product/   Frozen product definition
  technical/ Frozen technical specification and supporting notes
  tasks/     Engineering task definitions
tests/       Cross-project test space
```

## Local Development

### Web

```bash
cd apps/web
npm install
npm run dev
```

### API

```bash
cd apps/api
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API health endpoint is available at `http://localhost:8000/health`.

## TASK-002 Profile confirmation

Resume parsing now persists an editable `DRAFT` Profile. The profile API is:

```text
GET  /api/v1/profiles/{profile_id}
PUT  /api/v1/profiles/{profile_id}
POST /api/v1/profiles/{profile_id}/confirm
```

Set `DATABASE_URL` to a PostgreSQL connection for real persistence, then apply
the schema with Alembic:

```bash
cd apps/api
.\.venv\Scripts\alembic.exe -c alembic.ini upgrade head
```

`PUT` keeps a profile in `DRAFT`; only the explicit confirm endpoint changes it
to `CONFIRMED`. AI-extracted rows retain resume evidence, while user-entered
rows may omit evidence. Skill proficiency remains unset until the user selects
`AWARE`, `BASIC`, `PROJECT_READY`, or `PROFICIENT`.

## Verification

```bash
cd apps/web
npm run type-check
npm run build

cd ../api
pytest
```

SQLite in-memory fixtures are used only for fast service/API tests. The
PostgreSQL integration gate requires a dedicated `TEST_DATABASE_URL`:

```bash
$env:TEST_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/ai_career_os_test"
.\.venv\Scripts\python.exe -m pytest -m integration -q
```

If `TEST_DATABASE_URL` is absent, the integration test is skipped and the
PostgreSQL persistence gate remains unverified.
