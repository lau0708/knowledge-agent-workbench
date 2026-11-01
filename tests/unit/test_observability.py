import unittest

from src.agent.state import AgentStatus, AgentState, ToolCallStatus
from src.observability import (
    EvaluationCase,
    TraceStore,
    analyze_failure,
    build_trace,
    evaluate_state,
    run_regression,
)


class TraceRecordTest(unittest.TestCase):
    def test_build_trace_from_agent_state(self):
        state = AgentState.create("查询 RAG", session_id="s1")
        state.start()
        state.add_tool_call(
            name="search_knowledge_base",
            arguments={"query": "RAG"},
            result='{"count": 1}',
            status=ToolCallStatus.SUCCESS,
            tool_call_id="call_1",
        )
        state.mark_completed("RAG 是检索增强生成。")

        trace = build_trace(state)

        self.assertEqual(trace.session_id, "s1")
        self.assertEqual(trace.question, "查询 RAG")
        self.assertEqual(trace.status, "completed")
        self.assertEqual(len(trace.tool_calls), 1)
        self.assertEqual(trace.tool_calls[0]["name"], "search_knowledge_base")
        self.assertEqual(trace.answer, "RAG 是检索增强生成。")
        self.assertIsNone(trace.error)
        self.assertTrue(trace.trace_id)
        self.assertIsInstance(trace.duration_ms, int)

        payload = trace.to_dict()
        self.assertEqual(payload["trace_id"], trace.trace_id)
        self.assertEqual(payload["messages_count"], len(state.messages))

    def test_trace_store_isolates_sessions(self):
        store = TraceStore()

        first = AgentState.create("问题 A", session_id="s1")
        first.mark_completed("答案 A")
        second = AgentState.create("问题 B", session_id="s2")
        second.mark_completed("答案 B")

        store.add(build_trace(first))
        store.add(build_trace(second))

        self.assertEqual(len(store.list()), 2)
        self.assertEqual(len(store.list("s1")), 1)
        self.assertEqual(store.list("s1")[0].session_id, "s1")
        self.assertEqual(store.get(store.list("s1")[0].trace_id).question, "问题 A")


class FailureAnalysisTest(unittest.TestCase):
    def test_completed_state_has_no_failure(self):
        state = AgentState.create("普通问题")
        state.mark_completed("回答")

        result = analyze_failure(state)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["failure_stage"], "none")
        self.assertIsNone(result["error_type"])
        self.assertFalse(result["has_error"])

    def test_model_call_failure_is_classified(self):
        state = AgentState.create("查询知识库")
        state.mark_failed("模型调用失败：网络错误")

        result = analyze_failure(state)

        self.assertEqual(result["failure_stage"], "model_call")
        self.assertEqual(result["error_type"], "model_call_error")
        self.assertTrue(result["has_error"])

    def test_tool_failure_counts_as_retry(self):
        state = AgentState.create("删除文档")
        state.add_tool_call(
            name="delete_document",
            arguments={"document_id": 1},
            result='{"error": "工具执行失败：boom"}',
            status=ToolCallStatus.FAILED,
            error="工具执行失败：boom",
        )
        state.mark_failed("工具执行失败：boom")

        result = analyze_failure(state)

        self.assertEqual(result["failure_stage"], "tool_call")
        self.assertEqual(result["error_type"], "tool_execution_error")
        self.assertEqual(result["retry_count"], 1)
        self.assertEqual(result["failed_tool_count"], 1)

    def test_waiting_confirmation_stage(self):
        state = AgentState.create("删除文档")
        state.start()
        state.status = AgentStatus.WAITING_CONFIRMATION

        result = analyze_failure(state)

        self.assertEqual(result["failure_stage"], "confirmation_waiting")
        self.assertEqual(result["status"], "waiting_confirmation")

    def test_max_tool_rounds_stage(self):
        state = AgentState.create("循环调用工具")
        state.mark_failed("已达到最大工具调用轮数，任务未完成。")

        result = analyze_failure(state)

        self.assertEqual(result["failure_stage"], "max_tool_rounds")
        self.assertEqual(result["error_type"], "max_tool_rounds")

    def test_workflow_node_failure_stage(self):
        state = AgentState.create("工作流任务")
        state.add_workflow_event("retrieve", "failed", "连接失败")
        state.mark_failed("Workflow 节点失败：retrieve：连接失败")

        result = analyze_failure(state)

        self.assertEqual(result["failure_stage"], "workflow_node")
        self.assertEqual(result["error_type"], "workflow_node_error")
        self.assertEqual(result["failed_workflow_count"], 1)


class DeterministicEvaluationTest(unittest.TestCase):
    def _retrieval_state(self):
        state = AgentState.create("RAG 是什么", session_id="s1")
        state.start()
        state.add_tool_call(
            name="search_knowledge_base",
            arguments={"query": "RAG"},
            result=(
                '{"count": 1, "results": ['
                '{"source": "rag-intro.md", "score": 0.9, "content": "RAG"}]}'
            ),
            status=ToolCallStatus.SUCCESS,
            tool_call_id="call_1",
        )
        state.mark_completed("RAG 是检索增强生成。")
        return state

    def test_correct_tool_and_source_pass(self):
        case = EvaluationCase(
            case_id="rag_hit",
            question="RAG 是什么",
            expected_tool_names=["search_knowledge_base"],
            expected_sources=["rag-intro.md"],
        )

        result = evaluate_state(self._retrieval_state(), case)

        self.assertTrue(result["passed"], result["checks"])
        self.assertTrue(result["retrieval_hit"])
        self.assertEqual(result["actual_status"], "completed")

    def test_wrong_tool_selection_fails(self):
        state = AgentState.create("RAG 是什么")
        state.add_tool_call(
            name="echo",
            arguments={},
            result="{}",
            status=ToolCallStatus.SUCCESS,
        )
        state.mark_completed("回答")

        case = EvaluationCase(
            case_id="wrong_tool",
            question="RAG 是什么",
            expected_tool_names=["search_knowledge_base"],
        )

        result = evaluate_state(state, case)

        self.assertFalse(result["passed"])
        self.assertNotIn("search_knowledge_base", result["actual_tool_names"])
        self.assertFalse(any(check["passed"] for check in result["checks"] if check["name"].startswith("tool_called")))

    def test_status_mismatch_fails(self):
        state = AgentState.create("会失败")
        state.mark_failed("模型调用失败")

        case = EvaluationCase(case_id="status", question="会失败", expects_error=True)

        result = evaluate_state(state, case)

        self.assertFalse(result["passed"])
        self.assertFalse(any(check["passed"] for check in result["checks"] if check["name"] == "status"))


class RegressionRunnerTest(unittest.TestCase):
    def test_run_regression_summary(self):
        cases = [
            EvaluationCase(case_id="pass", question="正常"),
            EvaluationCase(
                case_id="fail",
                question="需要工具",
                expected_tool_names=["search_knowledge_base"],
            ),
        ]

        def runner(case):
            state = AgentState.create(case.question)
            if case.case_id == "pass":
                state.mark_completed("完成")
            else:
                state.mark_failed("失败")
            return state

        report = run_regression(cases, runner)

        self.assertEqual(report["total"], 2)
        self.assertEqual(report["passed"], 1)
        self.assertEqual(report["failed"], 1)
        self.assertEqual(report["pass_rate"], 0.5)


if __name__ == "__main__":
    unittest.main()
