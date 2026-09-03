# AI Career OS — TEST_EVAL_STRATEGY v1.0

**Status:** FROZEN

## 1. Software Tests

### Unit Tests
重点：
- priority scoring
- skill normalization helpers
- state transition rules
- schema validation

### Integration Tests
重点：
- Resume parse → Draft Profile
- JD parse → Market Profile
- Gap → Priority → Roadmap
- API + DB interaction

### E2E
MVP 只覆盖一条核心 Happy Path：
Resume → Confirm → JD → Gap → Roadmap → Task

## 2. AI Eval

AI 系统不能只测“代码有没有报错”。

### Resume Extraction
看：
- 字段正确性
- 是否漏信息
- 是否产生无依据技能

### JD Extraction
看：
- requirement extraction accuracy
- skill normalization consistency
- evidence_text 是否对应原文

### Gap Analysis
看：
- gap relevance
- evidence support
- actionable vs structural 分类

### Roadmap
看：
- 与 Top Gaps 的一致性
- 是否满足时间约束
- task 是否可执行
- completion criteria 是否明确

### RAG
看：
- retrieval relevance
- evidence recall
- groundedness
- citation correctness

## 3. Small Golden Set

首版建立一个小型人工标注集：
- 3–5 份 Resume
- 3 组 JD samples
- 若干预期 Gap
- 若干 RAG queries

它不是大规模 benchmark，而是防止 Prompt/模型升级后质量悄悄回退。

## Interview note

**Test** 检查软件行为是否正确；**Eval** 检查 AI 输出质量是否达到预期。
