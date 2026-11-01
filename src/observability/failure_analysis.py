from __future__ import annotations

from typing import Any

from src.agent.state import AgentState
from src.observability.tracing import TraceRecord, _duration_ms


def _as_dict(source: AgentState | TraceRecord | dict) -> dict:
    if isinstance(source, AgentState):
        return source.to_dict()

    if isinstance(source, TraceRecord):
        return source.to_dict()

    if isinstance(source, dict):
        return source

    raise TypeError("analyze_failure 只接受 AgentState、TraceRecord 或 dict")


def _status_value(status: Any) -> str:
    if hasattr(status, "value"):
        return str(status.value)
    return str(status or "")


def _tool_calls(payload: dict) -> list[dict]:
    records = payload.get("tool_calls") or []
    normalized = []

    for record in records:
        if hasattr(record, "to_dict"):
            normalized.append(record.to_dict())
        elif isinstance(record, dict):
            normalized.append(record)

    return normalized


def _workflow_events(payload: dict) -> list[dict]:
    events = payload.get("workflow_trace") or []
    return [event for event in events if isinstance(event, dict)]


def _classify_error(error: str | None) -> str | None:
    if not error:
        return None

    normalized = str(error)
    rules = [
        ("工具参数解析失败", "argument_parse_error"),
        ("工具参数校验失败", "tool_argument_error"),
        ("未注册的工具", "tool_not_found"),
        ("工具执行异常", "tool_execution_error"),
        ("工具执行失败", "tool_execution_error"),
        ("模型调用失败", "model_call_error"),
        ("最大工具调用轮数", "max_tool_rounds"),
        ("用户拒绝执行", "confirmation_rejected"),
        ("Workflow 节点失败", "workflow_node_error"),
        ("Workflow 超过最大步数", "workflow_max_steps"),
        ("检索结果不足", "insufficient_retrieval"),
    ]

    for marker, error_type in rules:
        if marker in normalized:
            return error_type

    return "unclassified_error"


def _failure_stage(
    status: str,
    error: str | None,
    tool_calls: list[dict],
    workflow_events: list[dict],
) -> str:
    if status == "waiting_confirmation":
        return "confirmation_waiting"

    if status != "failed":
        return "none"

    if any(call.get("status") == "failed" for call in tool_calls):
        return "tool_call"

    if any(event.get("event") == "failed" for event in workflow_events):
        return "workflow_node"

    normalized = str(error or "")
    if "模型调用失败" in normalized:
        return "model_call"
    if "最大工具调用轮数" in normalized:
        return "max_tool_rounds"
    if "用户拒绝执行" in normalized or "拒绝" in normalized:
        return "confirmation_rejected"

    return "unknown"


def analyze_failure(source: AgentState | TraceRecord | dict) -> dict:
    """把一次 Agent 执行转换成可定位的失败分析摘要。"""

    payload = _as_dict(source)
    status = _status_value(payload.get("status"))
    error = payload.get("error")
    tool_calls = _tool_calls(payload)
    workflow_events = _workflow_events(payload)

    failed_tool_count = sum(
        1 for call in tool_calls if call.get("status") == "failed"
    )
    failed_workflow_count = sum(
        1 for event in workflow_events if event.get("event") == "failed"
    )
    retry_count = failed_tool_count + failed_workflow_count

    duration_ms = payload.get("duration_ms")
    if duration_ms is None:
        duration_ms = _duration_ms(
            payload.get("created_at"),
            payload.get("updated_at"),
        )

    stage = _failure_stage(status, error, tool_calls, workflow_events)

    return {
        "status": status,
        "failure_stage": stage,
        "error_type": _classify_error(error),
        "error": error,
        "retry_count": retry_count,
        "failed_tool_count": failed_tool_count,
        "failed_workflow_count": failed_workflow_count,
        "duration_ms": duration_ms,
        "has_error": bool(error),
    }


def analyze_trace(trace: TraceRecord) -> dict:
    """TraceRecord 的便捷分析入口。"""

    return analyze_failure(trace)
