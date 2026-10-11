"""AI 求职助手「投投」路由：会话 CRUD、流式问答、岗位批量导入。

surface 区分「page（侧栏助手页）」与「orb（投投浮窗）」两套独立会话记录。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .assistant_service import build_client, build_system_prompt, execute_tool, tool_specs
from .database import get_db
from .mission_schemas import MissionCreate
from .mission_service import create_mission

logger = logging.getLogger("career_os.assistant_routes")

router = APIRouter(prefix="/api/v1")

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConversationCreate(BaseModel):
    surface: str = Field(default="page", pattern="^(page|orb)$")


class ConversationRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    surface: str
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    role: str
    content: str
    tool_calls: list | None = None
    sources: list | None = None
    created_at: datetime | None = None


class ConversationDetail(ConversationRead):
    messages: list[MessageRead] = Field(default_factory=list)


class ChatRequest(BaseModel):
    content: str = Field(min_length=1)
    profile_id: str | None = None
    mission_id: str | None = None
    web_search: bool = False
    allow_write: bool = False
    reasoning_effort: str = Field(default="medium", pattern="^(low|medium|high)$")


class ParseBatchRequest(BaseModel):
    raw_text: str = Field(min_length=1)


class JobDraft(BaseModel):
    title: str = ""
    company: str = ""
    role: str = ""
    location: str = ""
    description: str = ""


class BulkCreateRequest(BaseModel):
    drafts: list[JobDraft]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REASONING_NOTE = {
    "low": "回答尽量简洁、直接，点到为止。",
    "medium": "请先简要分析问题要点，再给出清晰回答。",
    "high": "请深入思考、多角度权衡后作答，给出更有深度的分析和可执行建议。",
}

_APPLICATION_STATUS_LABEL = {
    "PENDING": "待投递", "APPLIED": "已投递", "SCREENING": "筛选中",
    "ASSESSMENT": "测评/笔试", "INTERVIEW": "面试", "OFFER": "Offer", "CLOSED": "已结束",
}


def _conv_read(row: models.AssistantConversation) -> ConversationRead:
    return ConversationRead(
        id=str(row.id), surface=row.surface, title=row.title,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _message_read(row: models.AssistantMessage) -> MessageRead:
    return MessageRead(
        id=str(row.id), role=row.role, content=row.content,
        tool_calls=row.tool_calls, sources=row.sources, created_at=row.created_at,
    )


def _sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _conversation_or_404(db: Session, conversation_id: UUID, surface: str | None = None) -> models.AssistantConversation:
    row = db.get(models.AssistantConversation, conversation_id)
    if row is None or (surface is not None and row.surface != surface):
        raise HTTPException(status_code=404, detail="会话不存在")
    return row


# ---------------------------------------------------------------------------
# 会话 CRUD
# ---------------------------------------------------------------------------


@router.get("/assistant/conversations", response_model=list[ConversationRead])
def list_conversations(surface: str = Query(default="page", pattern="^(page|orb)$"), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(models.AssistantConversation)
        .where(models.AssistantConversation.surface == surface)
        .order_by(models.AssistantConversation.updated_at.desc())
    ).all()
    return [_conv_read(row) for row in rows]


@router.post("/assistant/conversations", response_model=ConversationRead, status_code=201)
def create_conversation(payload: ConversationCreate, db: Session = Depends(get_db)):
    row = models.AssistantConversation(surface=payload.surface)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _conv_read(row)


@router.get("/assistant/conversations/{conversation_id}", response_model=ConversationDetail)
def read_conversation(conversation_id: UUID, surface: str = Query(default="page"), db: Session = Depends(get_db)):
    row = _conversation_or_404(db, conversation_id, surface)
    messages = db.scalars(
        select(models.AssistantMessage)
        .where(models.AssistantMessage.conversation_id == row.id)
        .order_by(models.AssistantMessage.created_at, models.AssistantMessage.id)
    ).all()
    detail = ConversationDetail(
        id=str(row.id), surface=row.surface, title=row.title,
        created_at=row.created_at, updated_at=row.updated_at,
        messages=[_message_read(m) for m in messages],
    )
    return detail


@router.delete("/assistant/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: UUID, surface: str = Query(default="page"), db: Session = Depends(get_db)):
    row = _conversation_or_404(db, conversation_id, surface)
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# 流式问答
# ---------------------------------------------------------------------------


@router.post("/assistant/conversations/{conversation_id}/messages")
async def send_message(conversation_id: UUID, payload: ChatRequest, db: Session = Depends(get_db)):
    conversation = _conversation_or_404(db, conversation_id)
    surface = conversation.surface

    # 保存用户消息
    user_row = models.AssistantMessage(conversation_id=conversation.id, role="user", content=payload.content)
    db.add(user_row)
    if conversation.title == "新对话":
        title = " ".join(payload.content.split())
        conversation.title = (title[:36] + "…") if len(title) > 36 else title
    conversation.updated_at = datetime.now()
    db.commit()
    db.refresh(user_row)

    # 历史（供模型）
    history_rows = db.scalars(
        select(models.AssistantMessage)
        .where(models.AssistantMessage.conversation_id == conversation.id)
        .order_by(models.AssistantMessage.created_at, models.AssistantMessage.id)
    ).all()
    db.close()

    return StreamingResponse(
        _stream_chat(payload, conversation.id, surface, [(_message_read(m)) for m in history_rows[:-1]]),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _stream_chat(payload: ChatRequest, conversation_id: UUID, surface: str, history: list[MessageRead]) -> AsyncIterator[str]:
    client, model = build_client()
    system_prompt = build_system_prompt(web_search=payload.web_search)
    note = _REASONING_NOTE.get(payload.reasoning_effort, _REASONING_NOTE["medium"])
    system_prompt += f"\n\n【思考强度】{note}"

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for m in history[-20:]:
        messages.append({"role": m.role, "content": m.content})

    user_text = payload.content
    context_lines: list[str] = []
    if payload.mission_id:
        # 可选：把当前岗位上下文带进去
        from .mission_service import get_mission
        with next(get_db_gen()) as db2:
            try:
                mission = get_mission(db2, UUID(payload.mission_id))
                context_lines.append(f"用户当前正在查看的岗位：{mission.company} · {mission.role}")
            except Exception:  # noqa: BLE001
                pass
    if context_lines:
        user_text += "\n\n[当前上下文]\n" + "\n".join(context_lines)

    messages.append({"role": "user", "content": user_text})

    specs = tool_specs(allow_write=payload.allow_write, web_search=payload.web_search)

    full_text = ""
    tool_log: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []

    try:
        yield _sse({"type": "start", "conversation_id": str(conversation_id)})

        for _round in range(4):
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "stream": True,
            }
            if specs:
                kwargs["tools"] = specs

            stream = client.chat.completions.create(**kwargs)

            content_parts: list[str] = []
            tool_calls: dict[int, dict[str, Any]] = {}
            finish_reason = ""

            for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                finish_reason = choice.finish_reason or finish_reason
                if getattr(delta, "content", None):
                    content_parts.append(delta.content)
                    yield _sse({"type": "delta", "text": delta.content})
                if getattr(delta, "tool_calls", None):
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls:
                            tool_calls[idx] = {"id": tc.id or "", "name": (tc.function.name if tc.function else ""), "arguments": ""}
                        if tc.function and tc.function.arguments:
                            tool_calls[idx]["arguments"] += tc.function.arguments

            round_text = "".join(content_parts)
            # 若这一轮模型要调工具，其正文只是「开场白」（如"I'll check…"），
            # 最终答案在最后一轮才产生——只保留最后一轮正文，避免开场白混入回答。
            if not tool_calls:
                full_text = round_text
                break

            # 回填 assistant tool_calls 消息
            calls = [
                {
                    "id": c["id"] or f"call_{i}",
                    "type": "function",
                    "function": {"name": c["name"], "arguments": c["arguments"]},
                }
                for i, c in sorted(tool_calls.items())
            ]
            messages.append({"role": "assistant", "content": None, "tool_calls": calls})

            # 逐个执行工具
            for c in sorted(tool_calls.values()):
                name = c["name"]
                try:
                    args = json.loads(c["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                try:
                    with next(get_db_gen()) as db2:
                        result_text, changed, sources = execute_tool(name, args, db2, payload.profile_id)
                except ValueError as exc:
                    result_text = str(exc)
                    changed = False
                    sources = []
                except Exception as exc:  # noqa: BLE001
                    logger.warning("工具执行失败 %s：%s", name, exc)
                    result_text = f"工具执行失败：{exc}"
                    changed = False
                    sources = []

                tool_log.append({"name": name, "changed": changed, "summary": result_text[:200]})
                if sources:
                    all_sources.extend(sources)
                messages.append({"role": "tool", "tool_call_id": c["id"] or f"call_0", "content": result_text})
                yield _sse({
                    "type": "tool",
                    "name": name,
                    "changed": changed,
                    "summary": result_text[:200],
                })

            if all_sources:
                yield _sse({"type": "sources", "sources": all_sources[:8]})

        if not full_text.strip() and tool_log:
            full_text = "已完成：\n" + "\n".join(f"- {t['summary']}" for t in tool_log)

        # 落库助手消息
        with next(get_db_gen()) as db2:
            assistant_row = models.AssistantMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=full_text,
                tool_calls=tool_log or None,
                sources=all_sources or None,
            )
            db2.add(assistant_row)
            conv = db2.get(models.AssistantConversation, conversation_id)
            if conv:
                conv.updated_at = datetime.now()
            db2.commit()
            db2.refresh(assistant_row)
            message_read = _message_read(assistant_row).model_dump(mode="json")

        yield _sse({"type": "done", "message": message_read})

    except Exception as exc:  # noqa: BLE001
        logger.exception("助手流式回复出错")
        # 尽力落库错误消息
        try:
            with next(get_db_gen()) as db2:
                assistant_row = models.AssistantMessage(
                    conversation_id=conversation_id, role="assistant",
                    content=full_text or f"（回复出错：{exc}）", tool_calls=tool_log or None,
                )
                db2.add(assistant_row)
                db2.commit()
        except Exception:  # noqa: BLE001
            pass
        yield _sse({"type": "error", "message": str(exc)})


def get_db_gen():
    """流式期间请求会话已关闭，这里按需建独立会话（复用 database 的引擎缓存逻辑）。"""
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from .database import _engines

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("Profile persistence is not configured")
    engine = _engines.get(database_url)
    if engine is None:
        engine = create_engine(database_url, pool_pre_ping=True)
        _engines[database_url] = engine

    def _gen():
        session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    return _gen()


# ---------------------------------------------------------------------------
# 岗位批量导入
# ---------------------------------------------------------------------------


@router.post("/profiles/{profile_id}/job-missions/parse-batch", response_model=list[JobDraft])
def parse_job_batch(profile_id: UUID, payload: ParseBatchRequest, db: Session = Depends(get_db)):
    """把一大段粘贴文本拆分成多份岗位草稿（先用启发式分段，再用模型规整）。"""
    db.get(models.UserProfile, profile_id)  # 校验档案存在
    chunks = _split_jobs(payload.raw_text)
    if not chunks:
        raise HTTPException(status_code=422, detail="没有识别到岗位描述，请确认粘贴内容。")

    drafts: list[JobDraft] = []
    for chunk in chunks:
        draft = _normalize_draft(chunk)
        if draft.description.strip() or draft.role.strip() or draft.company.strip():
            drafts.append(draft)
    if not drafts:
        raise HTTPException(status_code=422, detail="没有识别到岗位描述，请确认粘贴内容。")
    return drafts


@router.post("/profiles/{profile_id}/job-missions/bulk-create", response_model=dict)
def bulk_create_job_missions(profile_id: UUID, payload: BulkCreateRequest, db: Session = Depends(get_db)):
    """把确认后的岗位草稿批量创建为 job mission（逐个走标准 JD 分析）。"""
    created: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for i, draft in enumerate(payload.drafts):
        raw_text = _draft_to_jd(draft)
        if len(raw_text.strip()) < 20:
            errors.append({"index": i, "error": "岗位描述过短"})
            continue
        try:
            mission = create_mission(db, profile_id, MissionCreate(raw_text=raw_text))
            created.append({"mission_id": str(mission.id), "company": draft.company or "", "role": draft.role or ""})
        except Exception as exc:  # noqa: BLE001
            logger.warning("批量创建岗位失败：%s", exc)
            errors.append({"index": i, "error": str(exc)})
    return {"created": created, "errors": errors, "total": len(payload.drafts)}


# --- 启发式分段与草稿规整 ---


def _split_jobs(raw_text: str) -> list[str]:
    import re

    text = raw_text.strip()
    if not text:
        return []
    # 以「岗位/职位/公司」开头 + 空行分隔，先按空行粗切，再按标题合并
    lines = text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []
    title_re = re.compile(r"^(岗位|职位|招聘|公司|【|\[)?[：: ]*(岗位|职位|招聘)[：:]", re.I)
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        if title_re.match(stripped) and current and len(current) > 2:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)

    # 若切得太碎（单行块）则退回整段为一块
    merged: list[str] = []
    for block in blocks:
        text_block = "\n".join(block).strip()
        if len(text_block) < 20:
            continue
        merged.append(text_block)
    if not merged and text:
        merged = [text]
    return merged


def _normalize_draft(chunk: str) -> JobDraft:
    import re

    lines = [l.strip() for l in chunk.splitlines() if l.strip()]
    company = role = location = ""
    for line in lines:
        m = re.search(r"公司[：:]\s*([^\s，,]+)", line)
        if m and not company:
            company = m.group(1)
        m = re.search(r"(岗位|职位|职位名称)[：:]\s*([^\s，,]+)", line)
        if m and not role:
            role = m.group(2)
        m = re.search(r"(地点|工作地点|城市)[：:]\s*([^\s，,]+)", line)
        if m and not location:
            location = m.group(2)
    # 兜底：首行常是「公司 - 岗位」
    if not role and lines:
        first = lines[0]
        if " - " in first:
            company = first.split(" - ")[0].strip()
            role = first.split(" - ")[1].strip()
        elif "｜" in first or " | " in first:
            parts = re.split(r"[｜|]", first)
            if len(parts) >= 2:
                company = parts[0].strip()
                role = parts[1].strip()
    title = f"{company} · {role}".strip(" ·") if (company or role) else "未命名岗位"
    return JobDraft(title=title, company=company, role=role, location=location, description=chunk)


def _draft_to_jd(draft: JobDraft) -> str:
    parts = [f"公司：{draft.company or 'UNKNOWN'}", f"岗位：{draft.role or 'UNKNOWN'}"]
    if draft.location:
        parts.append(f"地点：{draft.location}")
    parts.append("")
    parts.append("岗位描述：")
    parts.append(draft.description.strip() or "（岗位描述见原文）")
    return "\n".join(parts)


__all__ = ["router"]
