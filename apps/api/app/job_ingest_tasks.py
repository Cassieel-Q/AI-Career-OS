"""岗位采集任务：状态机 + 进度 + 取消。

UI 需要的是「一次采集任务」，而不是一次同步 HTTP 调用：

- ``POST /collect-runs``    创建任务 → 立即返回 ``task_id``（状态 RUNNING）
- ``GET  /collect-runs/{id}`` 轮询状态与部分结果
- ``POST /collect-runs/{id}/cancel`` 用户取消

任务状态：``IDLE / RUNNING / COMPLETED / PARTIAL / FAILED / CANCELLED``
结果状态：``NEW / DUPLICATE / UPDATED / NEEDS_REVIEW / FAILED``（见 ``classify_collected``）

执行策略：后台线程 + 独立的数据库 Session。每个来源之间检查一次取消标志与
时间上限，因此「取消」最多在下一个来源开始前生效，不会假装已停止而继续请求。
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from . import job_ingest_service as ingest

TASK_IDLE = "IDLE"
TASK_RUNNING = "RUNNING"
TASK_COMPLETED = "COMPLETED"
TASK_PARTIAL = "PARTIAL"
TASK_FAILED = "FAILED"
TASK_CANCELLED = "CANCELLED"

RESULT_STATES = ("NEW", "DUPLICATE", "UPDATED", "NEEDS_REVIEW", "FAILED")

DEFAULT_TIMEOUT_SECONDS = 120.0
MAX_TASKS = 40
TASK_TTL_MINUTES = 60


class CollectTask:
    def __init__(self, profile_id: str, request: dict) -> None:
        self.task_id = f"task-{uuid.uuid4().hex[:12]}"
        self.profile_id = profile_id
        self.request = request
        self.status = TASK_RUNNING
        self.created_at = datetime.now(timezone.utc)
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.progress: list[dict] = []
        self.result: dict | None = None
        self.error: str | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        # 轮询时看到的中间态：来源级别实时进度
        self.stage = "QUEUED"
        self.current_source: str | None = None
        self.fetched = 0

    # ------------------------------------------------------------------ 取消
    def cancel(self) -> None:
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    # ------------------------------------------------------------------ 快照
    def snapshot(self) -> dict:
        with self._lock:
            elapsed = None
            if self.started_at:
                until = self.finished_at or datetime.now(timezone.utc)
                elapsed = round((until - self.started_at).total_seconds(), 2)
            return {
                "task_id": self.task_id,
                "profile_id": self.profile_id,
                "status": self.status,
                "stage": self.stage,
                "current_source": self.current_source,
                "fetched": self.fetched,
                "created_at": self.created_at.isoformat(),
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None,
                "elapsed_seconds": elapsed,
                "request": self.request,
                "progress": list(self.progress[-50:]),
                "result": self.result,
                "error": self.error,
            }


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, CollectTask] = {}
        self._lock = threading.Lock()

    def put(self, task: CollectTask) -> None:
        with self._lock:
            self._tasks[task.task_id] = task
            self._evict()

    def get(self, task_id: str) -> CollectTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_recent(self, profile_id: str | None = None, limit: int = 10) -> list[dict]:
        with self._lock:
            items = list(self._tasks.values())
        if profile_id:
            items = [item for item in items if item.profile_id == profile_id]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return [item.snapshot() for item in items[:limit]]

    def _evict(self) -> None:
        """按数量与时间淘汰旧任务，避免长时间运行后无限增长。"""
        if len(self._tasks) <= MAX_TASKS:
            return
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=TASK_TTL_MINUTES)
        stale = [
            task_id
            for task_id, task in self._tasks.items()
            if task.finished_at is not None and task.finished_at < cutoff
        ]
        for task_id in stale[: max(0, len(self._tasks) - MAX_TASKS)]:
            self._tasks.pop(task_id, None)


STORE = TaskStore()


def _run(task: CollectTask) -> None:
    from .database import open_session

    task.started_at = datetime.now(timezone.utc)
    task.stage = "COLLECTING"

    def on_progress(event: dict) -> None:
        task.fetched = int(event.get("fetched", task.fetched))
        if event.get("source"):
            task.current_source = str(event.get("source"))
        event = dict(event)
        event["at"] = datetime.now(timezone.utc).isoformat()
        with task._lock:
            task.progress.append(event)

    try:
        result = ingest.run_collection(
            sources=task.request.get("sources") or [],
            keywords=task.request.get("keywords") or [],
            location=task.request.get("location"),
            employment_type=task.request.get("employment_type"),
            posted_within_days=task.request.get("posted_within_days"),
            limit=int(task.request.get("limit") or 20),
            greenhouse_boards=task.request.get("greenhouse_boards") or [],
            lever_companies=task.request.get("lever_companies") or [],
            timeout_seconds=float(task.request.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS),
            cancel_check=task.is_cancelled,
            progress=on_progress,
        )
    except Exception as exc:  # pragma: no cover - 兜底
        task.status = TASK_FAILED
        task.error = f"{exc.__class__.__name__}: {exc}"
        task.stage = "FAILED"
        task.finished_at = datetime.now(timezone.utc)
        return

    # 相对于现有岗位库标注 NEW / DUPLICATE / UPDATED / NEEDS_REVIEW / FAILED
    try:
        uuid.UUID(str(task.profile_id))
        session = open_session()
        try:
            ingest.classify_collected(session, uuid.UUID(str(task.profile_id)), result.get("jobs", []))
        finally:
            session.close()
        # 结果状态是在采集之后才标注的，统计必须在标注完成后重算，否则 new/duplicate 全是 0。
        result["totals"] = ingest.recompute_result_totals(result.get("totals", {}), result.get("jobs", []))
    except Exception as exc:  # pragma: no cover - 标注失败不应吞掉采集结果
        result.setdefault("warnings", []).append(f"结果状态标注失败：{exc}")

    if task.is_cancelled():
        task.status = TASK_CANCELLED
    else:
        task.status = result.get("status") or TASK_COMPLETED
    result["status"] = task.status
    result["task_id"] = task.task_id
    task.result = result
    task.stage = "FINISHED"
    task.finished_at = datetime.now(timezone.utc)


def submit(profile_id: str, request: dict) -> dict:
    """创建并启动一个采集任务（后台线程），立即返回任务快照。"""
    task = CollectTask(profile_id, request)
    STORE.put(task)
    worker = threading.Thread(target=_run, args=(task,), name=f"job-collect-{task.task_id}", daemon=True)
    worker.start()
    return task.snapshot()


def get_snapshot(task_id: str) -> dict | None:
    task = STORE.get(task_id)
    return task.snapshot() if task else None


def cancel_task(task_id: str) -> dict | None:
    task = STORE.get(task_id)
    if task is None:
        return None
    task.cancel()
    if task.status == TASK_RUNNING:
        task.stage = "CANCELLING"
    return task.snapshot()


def recent_tasks(profile_id: str | None = None, limit: int = 10) -> list[dict]:
    return STORE.list_recent(profile_id=profile_id, limit=limit)


__all__ = [
    "RESULT_STATES",
    "TASK_CANCELLED",
    "TASK_COMPLETED",
    "TASK_FAILED",
    "TASK_IDLE",
    "TASK_PARTIAL",
    "TASK_RUNNING",
    "cancel_task",
    "get_snapshot",
    "recent_tasks",
    "submit",
]
