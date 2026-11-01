from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PendingStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class PendingOperation:
    """等待人工确认的工具操作。"""

    operation_id: str
    session_id: str
    tool_name: str
    arguments: dict
    tool_call_id: str | None = None
    status: PendingStatus = PendingStatus.PENDING
    result: str | None = None
    error: str | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    expires_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "operation_id": self.operation_id,
            "session_id": self.session_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "tool_call_id": self.tool_call_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
        }


class HitlError(Exception):
    """HITL 通用错误。"""


class HitlConflictError(HitlError):
    """待确认操作状态冲突，例如重复批准或拒绝。"""


class HitlExecutionError(HitlError):
    """批准后执行工具失败。"""


class ConfirmationRequiredError(Exception):
    """工具需要人工确认，Agent 应暂停并等待用户决策。"""

    def __init__(self, operation_id: str, tool_name: str, session_id: str) -> None:
        self.operation_id = operation_id
        self.tool_name = tool_name
        self.session_id = session_id
        super().__init__(
            f"工具 {tool_name} 需要人工确认，operation_id={operation_id}"
        )
