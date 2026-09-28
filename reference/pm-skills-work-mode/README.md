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

## Verification

```bash
cd apps/web
npm run type-check
npm run build

cd ../api
pytest
```

This repository currently contains only the TASK-000 bootstrap. Business capabilities are intentionally not implemented.
