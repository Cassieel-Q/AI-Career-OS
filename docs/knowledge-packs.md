# Knowledge packs

AI Career OS keeps small, reviewable Markdown packs in `knowledge/resume_skills/` and `knowledge/interview_skills/`. They are inputs to the Resume and Interview Intelligence layers; they do not replace Profile evidence and they never create a claim by themselves.

## Frontmatter

Every file starts and ends its YAML frontmatter with `---`:

```yaml
id: LLM_EVALUATION
kind: interview_skill # resume_skill or interview_skill
name: LLM evaluation
version: 1.0.0
provenance: SYNTHETIC_DEMO_ONLY
company: Baidu # optional
roles: [AI Product Manager]
related_roles: [Product Manager]
role_family: AI_PRODUCT
competencies: [evaluation, quality]
source_count: 1
recency: 2026-01-01
source_refs: [synthetic-baidu-demo]
```

`id`, `kind`, `name`, `version`, `provenance`, and `competencies` are required by the validator. `source_count`, `recency`, and `source_refs` must describe the curated source metadata. Company packs in this repository are explicitly synthetic demo packs and must never be described as real company reports.

## Authoring rules

- Keep one competency or interview behavior per pack.
- Use evidence-grounded language: a pack may suggest a question pattern, never assert that a company *must* ask it.
- Keep generated resume suggestions tied to Profile/evidence refs; packs are not evidence.
- Increase `version` when the behavior or metadata changes and keep `source_refs` reviewable.
- Do not put Profile, JD, API key, or other personal data in a pack.

## Validate, reload, and sync

The loader is tolerant at the application boundary: malformed files are reported as structured diagnostics and valid packs continue to load. In Python:

```powershell
cd apps/api
..\..\ai-career-OS\apps\api\.venv\Scripts\python.exe -c "from app.knowledge_packs import sync_knowledge_packs; print(sync_knowledge_packs())"
```

`KnowledgePackRegistry.reload()` rescans the directory and recomputes SHA-256 fingerprints. The dogfood fixture calls this path before retrieval. A future deployment command may wrap `sync_knowledge_packs`; no database migration is needed for pack edits.

## Retrieval semantics

`InterviewIntelRetriever` ranks same company and role family first, then same company related role, same role family at another company, and generic AI PM packs. It returns source count, recency, confidence, and refs. UI copy uses **Observed in N curated reports** and avoids prescriptive “must ask” wording.

