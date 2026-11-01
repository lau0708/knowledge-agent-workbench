from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolCallStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    WAITING_CONFIRMATION = "waiting_confirmation"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ToolCallRecord:
    """单次工具调用的完整记录。"""

    name: str
    arguments: dict
    status: ToolCallStatus = ToolCallStatus.SUCCESS
    result: str | None = None
    error: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "tool_call_id": self.tool_call_id,
        }


@dataclass
class AgentState:
    """当前 Agent 任务执行状态，不等同于长期 Memory。"""

    session_id: str
    user_input: str
    status: AgentStatus = AgentStatus.PENDING
    messages: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    tool_call_count: int = 0
    workflow_trace: list[dict] = field(default_factory=list)
    pending_operation_id: str | None = None
    error: str | None = None
    answer: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    @classmethod
    def create(cls, user_input: str, session_id: str | None = None) -> "AgentState":
        return cls(
            session_id=session_id or uuid.uuid4().hex[:12],
            user_input=user_input,
        )

    def _touch(self) -> None:
        self.updated_at = _utc_now()

    def start(self) -> None:
        self.status = AgentStatus.RUNNING
        self._touch()

    def mark_completed(self, answer: str) -> None:
        self.answer = answer
        self.status = AgentStatus.COMPLETED
        self.error = None
        self._touch()

    def mark_failed(self, error: str) -> None:
        self.error = error
        self.status = AgentStatus.FAILED
        self._touch()

    def add_message(
        self,
        role: str,
        content: str | None = None,
        tool_calls: list[dict] | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        message: dict[str, Any] = {"role": role}

        if content is not None:
            message["content"] = content

        if tool_calls is not None:
            message["tool_calls"] = tool_calls

        if tool_call_id is not None:
            message["tool_call_id"] = tool_call_id

        self.messages.append(message)
        self._touch()

    def add_tool_call(
        self,
        name: str,
        arguments: dict,
        result: str,
        status: ToolCallStatus,
        error: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        record = ToolCallRecord(
            name=name,
            arguments=arguments,
            status=status,
            result=result,
            error=error,
            tool_call_id=tool_call_id,
        )

        self.tool_calls.append(record)
        self.tool_results.append(
            {
                "tool_call_id": tool_call_id,
                "name": name,
                "result": result,
                "status": status.value,
            }
        )
        self.tool_call_count += 1
        self._touch()

    def resolve_tool_call(
        self,
        tool_call_id: str | None,
        status: ToolCallStatus,
        result: str,
        error: str | None = None,
    ) -> None:
        """更新已等待确认的工具调用，不重复增加计数。"""

        for record in reversed(self.tool_calls):
            if record.tool_call_id == tool_call_id:
                record.status = status
                record.result = result
                record.error = error
                break

        for result_record in reversed(self.tool_results):
            if result_record.get("tool_call_id") == tool_call_id:
                result_record["result"] = result
                result_record["status"] = status.value
                break

        self._touch()

    def add_workflow_event(
        self,
        node: str,
        event: str,
        detail: str | None = None,
    ) -> None:
        self.workflow_trace.append(
            {
                "node": node,
                "event": event,
                "detail": detail,
            }
        )
        self._touch()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "user_input": self.user_input,
            "status": self.status.value,
            "messages": self.messages,
            "tool_calls": [record.to_dict() for record in self.tool_calls],
            "tool_results": self.tool_results,
            "tool_call_count": self.tool_call_count,
            "workflow_trace": self.workflow_trace,
            "pending_operation_id": self.pending_operation_id,
            "error": self.error,
            "answer": self.answer,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
