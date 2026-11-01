import uuid

from src.hitl.models import (
    ConfirmationRequiredError,
    HitlConflictError,
    HitlError,
    HitlExecutionError,
    PendingOperation,
    PendingStatus,
)
from src.hitl.store import PendingOperationStore
from src.tools.dispatcher import (
    ToolArgumentError,
    ToolDispatcher,
    ToolNotFoundError,
)


def should_confirm(tool) -> bool:
    """根据工具风险等级和显式配置判断是否需要人工确认。"""

    if tool.requires_confirmation is not None:
        return tool.requires_confirmation

    return tool.risk_level in {"high", "critical"}


class ConfirmationDispatcher:
    """与 ToolDispatcher 保持相同调用方式的 HITL 分发器。"""

    def __init__(self, service: "HitlService", registry, session_id: str) -> None:
        self.service = service
        self.registry = registry
        self.session_id = session_id

    def dispatch(self, name: str, arguments: dict, tool_call_id: str | None = None) -> str:
        return self.service.dispatch(
            self.registry,
            name,
            arguments,
            session_id=self.session_id,
            tool_call_id=tool_call_id,
        )


class HitlService:
    """管理待确认操作，批准后真正执行工具。"""

    def __init__(
        self,
        store: PendingOperationStore | None = None,
        timeout_seconds: int = 300,
    ) -> None:
        self.store = store or PendingOperationStore(timeout_seconds=timeout_seconds)

    def build_dispatcher(self, registry, session_id: str) -> ConfirmationDispatcher:
        return ConfirmationDispatcher(self, registry, session_id)

    def dispatch(
        self,
        registry,
        name: str,
        arguments: dict,
        session_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> str:
        tool = registry.get(name)

        if tool is not None and should_confirm(tool):
            operation_id = uuid.uuid4().hex[:12]
            session_id = session_id or "default"

            self.store.create(
                operation_id=operation_id,
                session_id=session_id,
                tool_name=name,
                arguments=arguments,
                tool_call_id=tool_call_id,
            )

            raise ConfirmationRequiredError(operation_id, name, session_id)

        return ToolDispatcher(registry).dispatch(
            name,
            arguments,
            tool_call_id=tool_call_id,
        )

    def get_operation(self, operation_id: str) -> PendingOperation | None:
        return self.store.get(operation_id)

    def list_operations(self, session_id: str | None = None) -> list[PendingOperation]:
        return self.store.list_operations(session_id)

    def modify(
        self,
        operation_id: str,
        arguments: dict,
    ) -> PendingOperation:
        operation = self.store.update_arguments(operation_id, arguments)

        if operation is None:
            self._raise_conflict_or_missing(operation_id, "只能修改待确认操作")

        return operation

    def approve(
        self,
        operation_id: str,
        registry,
        modified_arguments: dict | None = None,
    ) -> PendingOperation:
        if modified_arguments is not None:
            self.modify(operation_id, modified_arguments)

        operation = self.store.get(operation_id)

        if operation is None or operation.status != PendingStatus.PENDING:
            self._raise_conflict_or_missing(operation_id, "操作已被处理或不存在")

        try:
            tool = ToolDispatcher(registry).validate(
                operation.tool_name,
                operation.arguments,
            )
        except (ToolNotFoundError, ToolArgumentError) as exc:
            raise HitlExecutionError(f"工具参数校验失败：{exc}") from exc

        if not should_confirm(tool):
            raise HitlExecutionError("工具当前不需要人工确认，不能通过审批流程执行")

        operation = self.store.transition(
            operation_id,
            PendingStatus.PENDING,
            PendingStatus.APPROVED,
        )

        if operation is None:
            self._raise_conflict_or_missing(operation_id, "操作已被处理或不存在")

        try:
            result = ToolDispatcher(registry).dispatch(
                operation.tool_name,
                operation.arguments,
                tool_call_id=operation.tool_call_id,
            )
        except Exception as exc:
            self.store.finalize(
                operation_id,
                PendingStatus.FAILED,
                error="工具执行失败",
            )
            raise HitlExecutionError("工具执行失败") from exc

        self.store.finalize(
            operation_id,
            PendingStatus.EXECUTED,
            result=result,
        )

        operation = self.store.get(operation_id)
        return operation

    def reject(self, operation_id: str, reason: str | None = None) -> PendingOperation:
        operation = self.store.transition(
            operation_id,
            PendingStatus.PENDING,
            PendingStatus.REJECTED,
            error=reason or "用户拒绝执行",
        )

        if operation is None:
            self._raise_conflict_or_missing(operation_id, "操作已被处理或不存在")

        return operation

    def expire_stale(self) -> list[PendingOperation]:
        return self.store.expire_stale()

    def _raise_conflict_or_missing(self, operation_id: str, message: str) -> None:
        existing = self.store.get(operation_id)

        if existing is None:
            raise HitlError(f"待确认操作不存在：{operation_id}")

        raise HitlConflictError(
            f"{message}，当前状态：{existing.status.value}"
        )
