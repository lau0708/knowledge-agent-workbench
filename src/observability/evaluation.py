from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from src.agent.state import AgentState
from src.observability.tracing import TraceRecord


@dataclass
class EvaluationCase:
    """确定性的 Agent 回归测试用例。"""

    case_id: str
    question: str
    expected_tool_names: list[str] = field(default_factory=list)
    forbidden_tool_names: list[str] = field(default_factory=list)
    expected_status: str = "completed"
    expected_sources: list[str] = field(default_factory=list)
    requires_answer: bool = True
    expects_error: bool = False


def _as_payload(source: AgentState | TraceRecord | dict) -> dict:
    if isinstance(source, AgentState):
        return source.to_dict()

    if isinstance(source, TraceRecord):
        return source.to_dict()

    if isinstance(source, dict):
        return source

    raise TypeError("evaluate 只接受 AgentState、TraceRecord 或 dict")


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


def _walk_sources(value: Any, sources: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "source" and isinstance(item, str):
                sources.add(item)
            _walk_sources(item, sources)
        return

    if isinstance(value, list):
        for item in value:
            _walk_sources(item, sources)


def _extract_sources(payload: dict) -> set[str]:
    sources: set[str] = set()
    source_regex = re.compile(r'"source"\s*:\s*"([^"]+)"')

    def collect_text(text: str) -> None:
        sources.update(source_regex.findall(text))

        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return

        _walk_sources(parsed, sources)

    for call in _tool_calls(payload):
        result = call.get("result")
        if isinstance(result, str):
            collect_text(result)
        elif result is not None:
            _walk_sources(result, sources)

    for result_record in payload.get("tool_results") or []:
        result = result_record.get("result")
        if isinstance(result, str):
            collect_text(result)
        elif result is not None:
            _walk_sources(result, sources)

    for message in payload.get("messages") or []:
        content = message.get("content")
        if isinstance(content, str):
            collect_text(content)

    return sources


def _source_matches(actual: str, expected: str) -> bool:
    actual = str(actual).replace("\\", "/")
    expected = str(expected).replace("\\", "/")

    if actual == expected or expected in actual:
        return True

    return actual.rsplit("/", 1)[-1] == expected.rsplit("/", 1)[-1]


def _evaluate_payload(case: EvaluationCase, payload: dict) -> dict:
    tool_calls = _tool_calls(payload)
    actual_tool_names = [str(call.get("name") or "") for call in tool_calls]
    status = _status_value(payload.get("status"))
    answer = payload.get("answer")
    error = payload.get("error")
    actual_sources = _extract_sources(payload)

    checks: list[dict] = []

    def add_check(name: str, passed: bool, detail: str) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "detail": detail,
            }
        )

    for tool_name in case.expected_tool_names:
        add_check(
            f"tool_called:{tool_name}",
            tool_name in actual_tool_names,
            f"实际工具：{sorted(actual_tool_names)}",
        )

    for tool_name in case.forbidden_tool_names:
        add_check(
            f"tool_not_called:{tool_name}",
            tool_name not in actual_tool_names,
            f"实际工具：{sorted(actual_tool_names)}",
        )

    if case.expected_status:
        add_check(
            "status",
            status == case.expected_status,
            f"期望 {case.expected_status}，实际 {status}",
        )

    has_answer = bool(answer)
    if case.requires_answer:
        add_check("has_answer", has_answer, "要求返回最终答案")
    else:
        add_check("no_answer", not has_answer, "期望不返回最终答案")

    has_error = bool(error)
    if case.expects_error:
        add_check("has_error", has_error, f"错误信息：{error}")
    else:
        add_check("no_error", not has_error, f"错误信息：{error}")

    retrieval_hit = None
    if case.expected_sources:
        retrieval_hit = any(
            _source_matches(actual, expected)
            for expected in case.expected_sources
            for actual in actual_sources
        )
        add_check(
            "retrieval_hit",
            bool(retrieval_hit),
            f"期望命中 {case.expected_sources}，实际来源 {sorted(actual_sources)}",
        )

    return {
        "case_id": case.case_id,
        "question": case.question,
        "passed": all(check["passed"] for check in checks),
        "actual_tool_names": actual_tool_names,
        "actual_status": status,
        "has_answer": has_answer,
        "has_error": has_error,
        "retrieval_hit": retrieval_hit,
        "retrieved_sources": sorted(actual_sources),
        "checks": checks,
    }


def evaluate_state(state: AgentState, case: EvaluationCase) -> dict:
    """对 AgentState 执行一个确定性评估用例。"""

    return _evaluate_payload(case, state.to_dict())


def evaluate_trace(trace: TraceRecord, case: EvaluationCase) -> dict:
    """对 TraceRecord 执行一个确定性评估用例。"""

    return _evaluate_payload(case, trace.to_dict())
