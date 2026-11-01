import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.agent.state import AgentState


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _duration_ms(started_at: str | None, updated_at: str | None) -> int | None:
    start = _parse_iso(started_at)
    end = _parse_iso(updated_at)

    if start is None or end is None:
        return None

    return max(0, int((end - start).total_seconds() * 1000))


@dataclass
class TraceRecord:
    """一次 Agent 请求的完整可观测记录。"""

    trace_id: str
    session_id: str
    question: str
    status: str
    started_at: str
    updated_at: str
    duration_ms: int | None
    messages_count: int
    tool_calls: list[dict]
    workflow_trace: list[dict]
    answer: str | None
    error: str | None
    pending_operation_id: str | None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "question": self.question,
            "status": self.status,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "duration_ms": self.duration_ms,
            "messages_count": self.messages_count,
            "tool_calls": self.tool_calls,
            "workflow_trace": self.workflow_trace,
            "answer": self.answer,
            "error": self.error,
            "pending_operation_id": self.pending_operation_id,
            **self.extra,
        }


class TraceStore:
    """进程内 Trace 存储，便于查询最近执行记录。"""

    def __init__(self) -> None:
        self._traces: dict[str, TraceRecord] = {}
        self._lock = threading.Lock()

    def add(self, trace: TraceRecord) -> TraceRecord:
        with self._lock:
            self._traces[trace.trace_id] = trace
        return trace

    def get(self, trace_id: str) -> TraceRecord | None:
        with self._lock:
            return self._traces.get(trace_id)

    def list(self, session_id: str | None = None) -> list[TraceRecord]:
        with self._lock:
            traces = list(self._traces.values())

        if session_id is None:
            return sorted(traces, key=lambda item: item.started_at)

        return sorted(
            (item for item in traces if item.session_id == session_id),
            key=lambda item: item.started_at,
        )


def build_trace(state: AgentState, extra: dict | None = None) -> TraceRecord:
    """把 AgentState 转换为结构化 Trace。"""

    payload = state.to_dict()

    return TraceRecord(
        trace_id=uuid.uuid4().hex[:12],
        session_id=payload["session_id"],
        question=payload["user_input"],
        status=payload["status"],
        started_at=payload["created_at"],
        updated_at=payload["updated_at"],
        duration_ms=_duration_ms(payload["created_at"], payload["updated_at"]),
        messages_count=len(payload["messages"]),
        tool_calls=payload["tool_calls"],
        workflow_trace=payload["workflow_trace"],
        answer=payload["answer"],
        error=payload["error"],
        pending_operation_id=payload["pending_operation_id"],
        extra=extra or {},
    )
