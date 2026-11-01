import threading
from datetime import datetime, timedelta, timezone

from src.hitl.models import PendingOperation, PendingStatus


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class PendingOperationStore:
    """进程内待确认操作容器，提供原子状态迁移。"""

    def __init__(self, timeout_seconds: int = 300) -> None:
        self.timeout_seconds = timeout_seconds
        self._operations: dict[str, PendingOperation] = {}
        self._lock = threading.Lock()

    def create(
        self,
        operation_id: str,
        session_id: str,
        tool_name: str,
        arguments: dict,
        tool_call_id: str | None = None,
    ) -> PendingOperation:
        now = _utc_now()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=self.timeout_seconds)
        ).isoformat()

        operation = PendingOperation(
            operation_id=operation_id,
            session_id=session_id,
            tool_name=tool_name,
            arguments=arguments,
            tool_call_id=tool_call_id,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )

        with self._lock:
            self._operations[operation_id] = operation

        return operation

    def get(self, operation_id: str) -> PendingOperation | None:
        with self._lock:
            return self._operations.get(operation_id)

    def list_operations(self, session_id: str | None = None) -> list[PendingOperation]:
        with self._lock:
            operations = list(self._operations.values())

        if session_id is None:
            return sorted(operations, key=lambda item: item.created_at)

        return sorted(
            (item for item in operations if item.session_id == session_id),
            key=lambda item: item.created_at,
        )

    def transition(
        self,
        operation_id: str,
        expected_status: PendingStatus,
        new_status: PendingStatus,
        result: str | None = None,
        error: str | None = None,
    ) -> PendingOperation | None:
        with self._lock:
            operation = self._operations.get(operation_id)

            if operation is None or operation.status != expected_status:
                return None

            operation.status = new_status
            operation.updated_at = _utc_now()

            if result is not None:
                operation.result = result
            if error is not None:
                operation.error = error

            return operation

    def finalize(
        self,
        operation_id: str,
        status: PendingStatus,
        result: str | None = None,
        error: str | None = None,
    ) -> PendingOperation | None:
        with self._lock:
            operation = self._operations.get(operation_id)

            if operation is None:
                return None

            operation.status = status
            operation.updated_at = _utc_now()

            if result is not None:
                operation.result = result
            if error is not None:
                operation.error = error

            return operation

    def update_arguments(
        self,
        operation_id: str,
        arguments: dict,
    ) -> PendingOperation | None:
        with self._lock:
            operation = self._operations.get(operation_id)

            if operation is None or operation.status != PendingStatus.PENDING:
                return None

            operation.arguments = arguments
            operation.updated_at = _utc_now()
            return operation

    def expire_stale(self) -> list[PendingOperation]:
        now = _utc_now()
        expired = []

        with self._lock:
            for operation in self._operations.values():
                if (
                    operation.status == PendingStatus.PENDING
                    and operation.expires_at is not None
                    and operation.expires_at <= now
                ):
                    operation.status = PendingStatus.EXPIRED
                    operation.updated_at = now
                    operation.error = "确认超时"
                    expired.append(operation)

        return expired
