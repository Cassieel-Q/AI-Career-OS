"""AI 求职助手「顺顺」路由：会话 CRUD、流式问答、岗位批量导入。

surface 区分「page（侧栏助手页）」与「orb（顺顺浮窗）」两套独立会话记录。
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

    # DeepSeek 思考模型会先输出一段不展示的推理内容，导致「首字」要等十几秒，
    # 表现为「不是流式、生成完才一次性出来」。对话助手这里关闭思考以换取即时流式。
    import os
    _is_deepseek = "deepseek" in (os.getenv("OPENAI_BASE_URL") or "").casefold()
    _extra_body = {"thinking": {"type": "disabled"}} if _is_deepseek else None

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
            if _extra_body is not None:
                kwargs["extra_body"] = _extra_body

            stream = await client.chat.completions.create(**kwargs)

            content_parts: list[str] = []
            tool_calls: dict[int, dict[str, Any]] = {}
            finish_reason = ""

            async for chunk in stream:
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
                        result_text, changed, sources = execute_tool(
                            name, args, db2, payload.profile_id, conversation_id
                        )
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
        yield _sse({"type": "error", "message": _humanize_stream_error(exc)})
    finally:
        # 释放本次请求创建的异步 HTTP 连接，避免连接泄漏。
        try:
            await client.close()
        except Exception:  # noqa: BLE001
            pass


def _humanize_stream_error(exc: Exception) -> str:
    """把底层异常翻译成用户能看懂、可操作的中文提示。"""
    name = type(exc).__name__.casefold()
    text = str(exc)
    if "timeout" in name or "timeout" in text.casefold():
        return "模型响应超时（可能是网络或模型较慢）。请稍后重试，或把「思考强度」调低。"
    if "connection" in name or "connect" in text.casefold() or "proxy" in text.casefold():
        return "连接模型服务失败。请检查 API 地址 / 网络 / 代理配置后重试。"
    if "authentication" in name or "401" in text or "api key" in text.casefold():
        return "模型 API 鉴权失败，请在 .env 检查 OPENAI_API_KEY。"
    if "rate" in name or "429" in text:
        return "请求过于频繁（限速），请稍后再试。"
    return f"回复中断：{text}"[:300]


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
# 写入安全（目标七）：能力目录 + 提案 → 确认 → 执行 → 回执
# ---------------------------------------------------------------------------


class ProposalConfirmRequest(BaseModel):
    profile_id: str | None = None


@router.get("/assistant/capabilities")
def list_capabilities() -> list[dict]:
    """助手可用的写操作能力目录（含参数 schema 与敏感标记）。"""
    from .assistant_capabilities import capability_catalog

    return capability_catalog()


@router.get("/assistant/proposals")
def list_write_proposals(
    conversation_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(PROPOSED|CONFIRMED|REJECTED|EXECUTED)$"),
    db: Session = Depends(get_db),
) -> list[dict]:
    from .assistant_capabilities import list_proposals, proposal_read

    return [proposal_read(row) for row in list_proposals(db, conversation_id=conversation_id, status=status)]


@router.get("/assistant/proposals/{proposal_id}")
def read_write_proposal(proposal_id: UUID, db: Session = Depends(get_db)) -> dict:
    from .assistant_capabilities import get_proposal, proposal_read

    return proposal_read(get_proposal(db, proposal_id))


@router.post("/assistant/proposals/{proposal_id}/confirm")
def confirm_write_proposal(
    proposal_id: UUID,
    payload: ProposalConfirmRequest | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """用户确认写入提案 → 执行 → 返回操作回执。"""
    from .assistant_capabilities import confirm_proposal, get_proposal, proposal_read

    override = None
    if payload and payload.profile_id:
        override = UUID(payload.profile_id)
    confirm_proposal(db, proposal_id, profile_id=override)
    return proposal_read(get_proposal(db, proposal_id))


@router.post("/assistant/proposals/{proposal_id}/reject")
def reject_write_proposal(proposal_id: UUID, db: Session = Depends(get_db)) -> dict:
    from .assistant_capabilities import proposal_read, reject_proposal

    return proposal_read(reject_proposal(db, proposal_id))
