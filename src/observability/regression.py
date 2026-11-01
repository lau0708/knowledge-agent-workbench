from __future__ import annotations

from typing import Callable

from src.agent.state import AgentState
from src.observability.evaluation import EvaluationCase, _evaluate_payload
from src.observability.tracing import TraceRecord


def run_regression(
    cases: list[EvaluationCase],
    runner: Callable[[EvaluationCase], AgentState | TraceRecord | dict],
) -> dict:
    """运行固定回归集并输出可复现的通过/失败报告。"""

    results = []
    passed = 0

    for case in cases:
        try:
            output = runner(case)
        except Exception as exc:
            result = {
                "case_id": case.case_id,
                "question": case.question,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "checks": [],
            }
        else:
            if isinstance(output, AgentState):
                result = _evaluate_payload(case, output.to_dict())
            elif isinstance(output, TraceRecord):
                result = _evaluate_payload(case, output.to_dict())
            elif isinstance(output, dict):
                result = _evaluate_payload(case, output)
            else:
                result = {
                    "case_id": case.case_id,
                    "question": case.question,
                    "passed": False,
                    "error": "runner 返回了不支持的评估对象",
                    "checks": [],
                }

        results.append(result)
        if result.get("passed"):
            passed += 1

    total = len(cases)
    failed = total - passed

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total else 0.0,
        "results": results,
    }
