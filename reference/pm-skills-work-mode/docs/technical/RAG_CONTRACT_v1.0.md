# AI Career OS — RAG_CONTRACT v1.0

**Status:** FROZEN

## Purpose

RAG 只用于非结构化 Evidence Retrieval，不承担用户状态、精确统计或 Gap Priority 的 Source of Truth。

## Ingestion

```text
Document
→ text clean
→ semantic chunking
→ metadata
→ embedding
→ PostgreSQL + pgvector
```

### Default chunking
- 首版按自然段/小节优先切分
- 目标 chunk 大小约 400–700 tokens
- overlap 约 80 tokens
- 不跨来源文档合并 chunk

### Required metadata
- document_id
- source_type
- career_plan_id
- source_url?
- jd_id?
- chunk_index

## Retrieval

```text
Query
→ embedding
→ metadata filter
→ vector similarity
→ top-k
→ evidence chunks
→ grounded LLM response
```

### Default retrieval
- initial top_k = 5
- 允许先过滤 `career_plan_id`
- 需要时再过滤 `source_type`
- 不在 v1 引入 reranker / hybrid BM25

## Why these defaults

这些值不是“最优参数”，而是首版可测试基线。真正参数由 Retrieval Eval 调整。

## RAG Evaluation

重点看：
1. **Retrieval Recall**：正确证据有没有被找回来。
2. **Precision / Relevance**：返回的 chunk 是否真的相关。
3. **Groundedness**：最终回答是否被检索证据支持。
4. **Citation correctness**：引用是否指向真实来源。

## Interview note

RAG 不是“把所有 PDF 都 embedding”。本项目把结构化事实留在 PostgreSQL，把非结构化 Evidence 放入向量检索。
