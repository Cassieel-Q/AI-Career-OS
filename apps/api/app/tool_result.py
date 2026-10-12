"""结构化工具结果（第八阶段）：所有助手工具执行统一返回 ``ToolResult``。

字段：
- ``name`` / ``arguments``：被调用的工具与其入参（可回溯）；
- ``ok``：本次调用是否成功；
- ``summary``：给用户看的简短结果；
- ``error``：失败原因（成功时为 None）；
- ``changed``：是否改动了数据（写工具改为提案后恒为 False）；
- ``source_refs``：来源列表（用于前端展示与回溯）。

兼容性：``ToolResult`` 支持按旧的三元组 ``(text, changed, sources)`` 解包，
避免破坏既有调用点。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class ToolResult:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    summary: str = ""
    error: str | None = None
    changed: bool = False
    source_refs: list[dict[str, Any]] = field(default_factory=list)

    # -- 兼容旧调用：text, changed, sources = execute_tool(...) --------------
    def __iter__(self) -> Iterator[Any]:
        yield self.summary
        yield self.changed
        yield self.source_refs

    @property
    def content_for_model(self) -> str:
        """回填给模型的工具消息正文。失败时把原因写清楚，便于模型降级作答。"""
        if self.ok:
            return self.summary
        return f"工具 {self.name} 执行失败：{self.error or '未知错误'}。请基于已有上下文继续回答，并如实说明该项未加载成功。"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "summary": self.summary,
            "error": self.error,
            "changed": self.changed,
            "source_refs": self.source_refs,
        }


def ok_result(
    name: str,
    summary: str,
    *,
    arguments: dict[str, Any] | None = None,
    changed: bool = False,
    source_refs: list[dict[str, Any]] | None = None,
) -> ToolResult:
    return ToolResult(
        name=name,
        arguments=arguments or {},
        ok=True,
        summary=summary,
        error=None,
        changed=changed,
        source_refs=list(source_refs or []),
    )


def failed_result(
    name: str,
    error: str,
    *,
    arguments: dict[str, Any] | None = None,
    summary: str | None = None,
) -> ToolResult:
    return ToolResult(
        name=name,
        arguments=arguments or {},
        ok=False,
        summary=summary or f"{name} 未执行成功：{error}",
        error=error,
        changed=False,
        source_refs=[],
    )


__all__ = ["ToolResult", "ok_result", "failed_result"]
