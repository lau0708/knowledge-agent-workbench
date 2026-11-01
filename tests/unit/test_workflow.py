import unittest

from src.agent.state import AgentState, AgentStatus
from src.agent.workflow import (
    NodeResult,
    Workflow,
    WorkflowNode,
    run_knowledge_workflow,
)


def make_state(question: str = "任务") -> AgentState:
    return AgentState.create(question)


def completed_nodes(state: AgentState) -> list[str]:
    return [
        event["node"]
        for event in state.workflow_trace
        if event["event"] == "completed"
    ]


class WorkflowEngineTest(unittest.TestCase):
    def test_sequential_execution_passes_result(self):
        def handler(name: str):
            def run(state, context):
                context.setdefault("path", []).append(name)
                return NodeResult(output=name)

            return run

        workflow = Workflow(
            nodes=[
                WorkflowNode("a", handler("a"), next_node="b"),
                WorkflowNode("b", handler("b"), next_node="c"),
                WorkflowNode("c", handler("c")),
            ],
            start_node="a",
            max_steps=10,
        )

        state = make_state()
        context = {}
        workflow.run(state, context)

        self.assertEqual(context["path"], ["a", "b", "c"])
        self.assertEqual(completed_nodes(state), ["a", "b", "c"])

    def test_conditional_routing_chooses_branch(self):
        def branch_handler(name: str):
            def run(state, context):
                context.setdefault("path", []).append(name)
                return NodeResult(output=name)

            return run

        def decide(state, context):
            return NodeResult(next_node="left" if context["go_left"] else "right")

        workflow = Workflow(
            nodes=[
                WorkflowNode("decide", decide),
                WorkflowNode("left", branch_handler("left")),
                WorkflowNode("right", branch_handler("right")),
            ],
            start_node="decide",
            max_steps=10,
        )

        left_state = make_state()
        workflow.run(left_state, {"go_left": True})
        self.assertEqual(completed_nodes(left_state), ["decide", "left"])

        right_state = make_state()
        workflow.run(right_state, {"go_left": False})
        self.assertEqual(completed_nodes(right_state), ["decide", "right"])

    def test_loop_terminates_when_handler_stops_routing(self):
        def loop(state, context):
            context["count"] = context.get("count", 0) + 1
            if context["count"] >= 2:
                return NodeResult(next_node=None)
            return NodeResult(next_node="loop")

        workflow = Workflow(
            nodes=[WorkflowNode("loop", loop)],
            start_node="loop",
            max_steps=10,
        )

        state = make_state()
        workflow.run(state, {"count": 0})

        self.assertEqual(state.status, AgentStatus.RUNNING)
        self.assertEqual(completed_nodes(state), ["loop", "loop"])

    def test_max_steps_prevents_infinite_loop(self):
        def loop(state, context):
            return NodeResult(next_node="loop")

        workflow = Workflow(
            nodes=[WorkflowNode("loop", loop)],
            start_node="loop",
            max_steps=3,
        )

        state = make_state()
        workflow.run(state, {})

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertIn("超过最大步数", state.error)


class KnowledgeWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.analyze = lambda question: {
            "needs_retrieval": True,
            "query": "RAG",
        }

    def test_success_path_writes_answer_and_status(self):
        results = [
            {
                "chunk_id": "chunk_1",
                "source": "rag.md",
                "content": "RAG 通过检索增强生成。",
                "score": 0.85,
            }
        ]

        state = run_knowledge_workflow(
            "查找 RAG 资料",
            model=object(),
            collection=object(),
            context_overrides={
                "analyze_intent": self.analyze,
                "search": lambda query, top_k: results,
                "generate_summary": lambda question, results: "RAG 总结",
            },
        )

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(state.answer, "RAG 总结")
        self.assertEqual(
            completed_nodes(state),
            ["analyze", "retrieve", "check_sufficiency", "summarize"],
        )
        self.assertEqual(state.messages[-1]["content"], "RAG 总结")

    def test_insufficient_result_triggers_supplement_retrieval(self):
        calls = []

        def search_fn(query, top_k):
            calls.append(query)
            if len(calls) == 1:
                return [{"chunk_id": "c1", "content": "低相关", "score": 0.1}]
            return [{"chunk_id": "c2", "content": "高相关", "score": 0.9}]

        state = run_knowledge_workflow(
            "查找 RAG 资料",
            model=object(),
            collection=object(),
            context_overrides={
                "analyze_intent": self.analyze,
                "search": search_fn,
                "generate_summary": lambda question, results: "补充后总结",
            },
        )

        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(len(calls), 2)
        self.assertIn("补充检索", calls[1])
        self.assertEqual(
            completed_nodes(state),
            [
                "analyze",
                "retrieve",
                "check_sufficiency",
                "supplement",
                "retrieve",
                "check_sufficiency",
                "summarize",
            ],
        )

    def test_max_supplement_attempts_stops_loop(self):
        state = run_knowledge_workflow(
            "查找不存在的资料",
            model=object(),
            collection=object(),
            context_overrides={
                "analyze_intent": self.analyze,
                "search": lambda query, top_k: [
                    {"chunk_id": "c1", "content": "低相关", "score": 0.1}
                ],
                "max_supplement_attempts": 2,
            },
        )

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertIn("检索结果不足", state.error)
        self.assertIn("insufficient", completed_nodes(state))
        self.assertNotIn("summarize", completed_nodes(state))

    def test_retrieval_failure_is_retried_then_terminated(self):
        def search_fn(query, top_k):
            raise RuntimeError("embedding 模型加载失败")

        state = run_knowledge_workflow(
            "查找 RAG 资料",
            model=object(),
            collection=object(),
            context_overrides={
                "analyze_intent": self.analyze,
                "search": search_fn,
                "max_supplement_attempts": 2,
            },
        )

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertIn("embedding 模型加载失败", state.error)
        self.assertEqual(completed_nodes(state).count("retrieve"), 2)

    def test_summary_model_failure_marks_workflow_failed(self):
        results = [{"chunk_id": "c1", "content": "相关资料", "score": 0.9}]

        def generate_summary(question, results):
            raise RuntimeError("DeepSeek 调用超时")

        state = run_knowledge_workflow(
            "查找 RAG 资料",
            model=object(),
            collection=object(),
            context_overrides={
                "analyze_intent": self.analyze,
                "search": lambda query, top_k: results,
                "generate_summary": generate_summary,
                "max_summary_retries": 1,
            },
        )

        self.assertEqual(state.status, AgentStatus.FAILED)
        self.assertIn("summarize", state.error)
        self.assertIn("DeepSeek 调用超时", state.error)


if __name__ == "__main__":
    unittest.main()
