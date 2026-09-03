# AI Career OS — Pre-Codex Baseline 替换说明

**基线版本**：Pre-Codex Baseline v1.0  
**日期**：2026-09-03

本包把此前分散的 PRD、DECISIONS、BACKLOG 与最新技术方向合并为 Codex 开工前的唯一权威文档集。

## 建议目录

```text
AI-Career-OS/
├── docs/
│   ├── product/
│   │   ├── PROJECT_KICKOFF.md
│   │   ├── PRD_v1.0_FINAL_FROZEN.md
│   │   ├── BACKLOG.md
│   │   ├── DECISIONS.md
│   │   ├── PRODUCT_GLOSSARY.md
│   │   └── CHANGELOG.md
│   └── technical/
│       ├── TECH_SPEC_v0.1.md
│       ├── DEVELOPMENT_WORKFLOW.md
│       └── CODEX_READINESS.md
└── REPLACE_GUIDE.md
```

## 替换规则

旧的 PRD 草稿、Final Review 临时报告、`DECISIONS_v1.1.md`、`BACKLOG_v1.1_ADDITIONS.md` 等可以归档，但开发时只参考本包中的 canonical 文件。

## 当前 Source of Truth

- 产品：`docs/product/PRD_v1.0_FINAL_FROZEN.md`
- 决策：`docs/product/DECISIONS.md`
- 延后需求：`docs/product/BACKLOG.md`
- 技术：`docs/technical/TECH_SPEC_v0.1.md`

`TECH_SPEC_v0.1.md` 仍是 DRAFT。完成 Data Model、API Contract、LLM/RAG Contract、Error Handling、Test Strategy 后才冻结为 v1.0。

Codex **暂时不能写业务代码**。Tech Spec 冻结后先执行 `TASK-000 — Repository Bootstrap`。
