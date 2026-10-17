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
from .assistant_service import assistant_settings, build_client, build_system_prompt, execute_tool, supports_tools, tool_specs
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
    # 第三阶段：前端进入助手时自动带入岗位版简历与来源路由。
    target_resume_id: str | None = None
    route: str | None = None
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
    from .model_config_service import ModelConfigError, ModelNotConfiguredError, ModelUnusableError
    from .secret_store import SecretStoreError

    try:
        client, model = build_client()
        settings = assistant_settings()
    except (ModelNotConfiguredError, ModelUnusableError, ModelConfigError, SecretStoreError) as exc:
        yield _sse({"type": "error", "message": str(exc)})
        return

    system_prompt = build_system_prompt(web_search=payload.web_search)
    note = _REASONING_NOTE.get(payload.reasoning_effort, _REASONING_NOTE["medium"])
    system_prompt += f"\n\n【思考强度】{note}"

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for m in history[-20:]:
        messages.append({"role": m.role, "content": m.content})

    user_text = payload.content
    context_lines: list[str] = []
    if payload.mission_id:
        # 可选：把当前岗位上下文带进去（任何失败都不能让流中断）。
        from .mission_service import get_mission
        try:
            with next(get_db_gen()) as db2:
                mission = get_mission(db2, UUID(payload.mission_id))
                context_lines.append(f"用户当前正在查看的岗位：{mission.company} · {mission.role}")
        except Exception:  # noqa: BLE001
            logger.warning("读取岗位上下文失败，跳过", exc_info=True)

    # 第一阶段：解析面试上下文（intent / 岗位 / 目标简历 / 置信度 / 缺失项）。
    resolved: dict[str, Any] | None = None
    try:
        from .interview_context import resolve_interview_context

        with next(get_db_gen()) as db2:
            resolved_ctx = resolve_interview_context(
                db2,
                message=payload.content,
                route=payload.route,
                mission_id=payload.mission_id,
                target_resume_id=payload.target_resume_id,
                profile_id=payload.profile_id,
                history=[{"role": m.role, "content": m.content} for m in history[-10:]],
            )
        resolved = resolved_ctx.to_dict()
        context_lines.append(_render_resolved_context(resolved))
    except Exception as exc:  # noqa: BLE001
        logger.warning("解析面试上下文失败：%s", exc)

    if context_lines:
        user_text += "\n\n[当前上下文]\n" + "\n".join(context_lines)

    messages.append({"role": "user", "content": user_text})

    # 模型明确不支持工具调用时，不传 tools（绝不能假装工具调用成功）
    if supports_tools(settings):
        specs = tool_specs(allow_write=payload.allow_write, web_search=payload.web_search)
    else:
        specs = []
        system_prompt += (
            "\n\n【重要】当前模型不支持工具调用（function calling），因此本轮**没有读取任何系统数据**。"
            "你必须如实说明：无法查询岗位/简历/面经等数据，只能基于用户本轮提供的信息回答，不要编造数据。"
        )
        yield _sse({"type": "degraded", "reasons": ["当前模型不支持工具调用，本轮未读取系统数据"]})

    # DeepSeek 思考模型会先输出一段不展示的推理内容，导致「首字」要等十几秒，
    # 表现为「不是流式、生成完才一次性出来」。对话助手这里关闭思考以换取即时流式。
    _extra_body = {"thinking": {"type": "disabled"}} if settings.is_deepseek else None

    full_text = ""
    tool_log: list[dict[str, Any]] = []
    all_sources: list[dict[str, Any]] = []
    degraded = False
    degraded_reasons: list[str] = []
    # 目标一/二：本轮解析出的面试上下文（供 Agent 固定流程与降级回答使用）。
    resolved_context: dict[str, Any] | None = None

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

            # 按 tool call index 排序（**不能**对 dict 排序：多个工具调用时
            # `sorted(tool_calls.values())` 会抛 '<' not supported between instances of
            # 'dict' and 'dict'，导致整轮流式回复中断）。
            ordered_calls = [tool_calls[idx] for idx in sorted(tool_calls.keys())]
            calls = [
                {
                    "id": c["id"] or f"call_{i}",
                    "type": "function",
                    "function": {"name": c["name"], "arguments": c["arguments"]},
                }
                for i, c in enumerate(ordered_calls)
            ]
            messages.append({"role": "assistant", "content": None, "tool_calls": calls})

            # 逐个执行工具：严格按 index 顺序，与上面 calls 一一对应。
            for i, c in enumerate(ordered_calls):
                name = c["name"]
                try:
                    args = json.loads(c["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                with next(get_db_gen()) as db2:
                    result = execute_tool(
                        name, args, db2, payload.profile_id, conversation_id, default_context=resolved
                    )

                # 目标八：单个工具失败不得终止整轮，把失败原因回给模型继续作答。
                tool_log.append({
                    "name": name,
                    "changed": result.changed,
                    "summary": result.summary[:200],
                    "ok": result.ok,
                    "error": result.error,
                })
                if result.source_refs:
                    all_sources.extend(result.source_refs)
                if not result.ok:
                    degraded = True
                    if result.error:
                        degraded_reasons.append(f"{name}: {result.error}")
                messages.append({"role": "tool", "tool_call_id": calls[i]["id"], "content": result.content_for_model})
                yield _sse({
                    "type": "tool",
                    "name": name,
                    "changed": result.changed,
                    "ok": result.ok,
                    "error": result.error,
                    "summary": result.summary[:200],
                })

            if all_sources:
                yield _sse({"type": "sources", "sources": all_sources[:8]})

        if not full_text.strip() and tool_log:
            full_text = "已完成：\n" + "\n".join(f"- {t['summary']}" for t in tool_log)

        # 目标八：工具失败不显示「回复中断」作为唯一结果——明确说明哪些内容没加载成功，
        # 并保留已成功加载的上下文继续作答。
        if degraded:
            missing_note = "；".join(dict.fromkeys(degraded_reasons)) or "部分工具未执行成功"
            full_text = (full_text or "").strip()
            full_text = (
                (full_text + "\n\n" if full_text else "")
                + f"⚠️ 部分资料本次未加载成功（{missing_note}）。以上回答基于已成功加载的内容；"
                "未加载成功的部分我已明确标出，你可以重试或直接告诉我缺失的信息。"
            )
            yield _sse({"type": "degraded", "reasons": list(dict.fromkeys(degraded_reasons))})

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
        # 尽力落库：保留已完成内容和工具记录，避免「答到一半」的成果丢失（第八阶段）。
        try:
            fallback = full_text.strip()
            if not fallback and tool_log:
                fallback = "已完成：\n" + "\n".join(f"- {t['summary']}" for t in tool_log)
            with next(get_db_gen()) as db2:
                assistant_row = models.AssistantMessage(
                    conversation_id=conversation_id, role="assistant",
                    content=fallback or f"（回复出错：{exc}）",
                    tool_calls=tool_log or None,
                    sources=all_sources or None,
                )
                db2.add(assistant_row)
                conv = db2.get(models.AssistantConversation, conversation_id)
                if conv:
                    conv.updated_at = datetime.now()
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


def _render_resolved_context(resolved: dict[str, Any]) -> str:
    """把解析出的面试上下文渲染成注入给模型的紧凑文本（不要求用户重录岗位）。"""
    lines = ["【本轮面试上下文（后端已解析，直接使用，不要要求用户重新录入）】"]
    if resolved.get("intent"):
        lines.append(f"- 意图：{resolved['intent']}")
    if resolved.get("company") or resolved.get("role"):
        lines.append(f"- 岗位：{resolved.get('company') or '未识别'} · {resolved.get('role') or '未识别'}")
    if resolved.get("mission_id"):
        lines.append(f"- 已匹配岗位 mission_id：{resolved['mission_id']}")
    else:
        lines.append("- 未匹配到已有岗位：若本轮附了 JD，就用它作为临时岗位上下文继续回答。")
    if resolved.get("target_resume_id"):
        lines.append(f"- 目标简历 target_resume_id：{resolved['target_resume_id']}")
    else:
        lines.append("- 当前岗位没有绑定岗位版简历：请明确说明，并改用已确认个人资料 + 本轮 JD 继续。")
    if resolved.get("jd_in_message"):
        lines.append("- 用户在消息里粘贴了完整 JD：直接使用，不要再要求提供岗位信息。")
    if resolved.get("crash_prep"):
        lines.append("- 检测到「今天/马上要面试」：进入短时准备模式（CRASH_PREP），先给最高优先级内容，不要长篇泛泛建议。")
    if resolved.get("candidates"):
        names = "、".join(f"{c.get('company')} {c.get('role')}" for c in resolved["candidates"][:5])
        lines.append(f"- 同公司多岗位候选（必须让用户确认，不要随机选）：{names}")
    if resolved.get("reason"):
        lines.append(f"- 解析说明：{resolved['reason']}")
    return "\n".join(lines)


def _humanize_stream_error(exc: Exception) -> str:
    """把底层异常翻译成用户能看懂、可操作的中文提示。"""
    name = type(exc).__name__.casefold()
    text = str(exc)
    if "timeout" in name or "timeout" in text.casefold():
        return "模型响应超时（可能是网络或模型较慢）。请稍后重试，或把「思考强度」调低。"
    if "connection" in name or "connect" in text.casefold() or "proxy" in text.casefold():
        return "连接模型服务失败。请检查 API 地址 / 网络 / 代理配置后重试。"
    if "authentication" in name or "401" in text or "api key" in text.casefold():
        return "模型 API 鉴权失败（401）。请到「设置 → AI 模型」测试连接，确认 API Key 仍然有效。"
    if "rate" in name or "429" in text:
        return "请求过于频繁（限速），请稍后再试。"
    return f"回复中断：{text}"[:300]


def get_db_gen():
    """流式期间请求会话已关闭，这里按需建独立会话（与 get_db 同一套「本地优先」解析）。

    之前直接读 DATABASE_URL，本地模式（AI_CAREER_DATA_DIR + 数据集指针）下没有
    这个环境变量，导致 SSE 流中途抛 RuntimeError，前端表现为 network error。
    """
    from app.local_mode import resolve_database_url

    from .database import _engines

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    database_url = resolve_database_url()
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


# ---------------------------------------------------------------------------
# 面试上下文（第一/二/三/四阶段）：解析 + 统一上下文 + 准备流程
# ---------------------------------------------------------------------------


class ContextResolveRequest(BaseModel):
    message: str = Field(default="", max_length=20_000)
    profile_id: str | None = None
    mission_id: str | None = None
    target_resume_id: str | None = None
    route: str | None = None


@router.post("/assistant/interview-context")
def resolve_context(payload: ContextResolveRequest, db: Session = Depends(get_db)) -> dict:
    """解析当前面试上下文并返回统一上下文摘要（供助手顶部上下文条使用）。"""
    from .interview_context import resolve_interview_context
    from .mission_interview_context import build_mission_interview_context, context_summary

    resolved = resolve_interview_context(
        db,
        message=payload.message,
        route=payload.route,
        mission_id=payload.mission_id,
        target_resume_id=payload.target_resume_id,
        profile_id=payload.profile_id,
    )
    result: dict[str, Any] = {"resolved": resolved.to_dict(), "summary": None, "prep": None}
    if payload.profile_id:
        try:
            profile_uuid = UUID(payload.profile_id)
        except (ValueError, TypeError):
            profile_uuid = None
        if profile_uuid is not None:
            mission_uuid = UUID(resolved.mission_id) if resolved.mission_id else None
            resume_uuid = UUID(resolved.target_resume_id) if resolved.target_resume_id else None
            ctx = build_mission_interview_context(
                db,
                profile_id=profile_uuid,
                mission_id=mission_uuid,
                target_resume_id=resume_uuid,
                raw_jd=resolved.raw_jd,
                company=resolved.company,
                role=resolved.role,
            )
            result["summary"] = context_summary(ctx)
            from .interview_prep_planner import plan_interview_prep

            result["prep"] = plan_interview_prep(resolved.to_dict(), ctx)
    return result
