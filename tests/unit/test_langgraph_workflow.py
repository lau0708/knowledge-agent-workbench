import unittest

from src.agent.langgraph_workflow import run_langgraph_workflow
from src.agent.state import AgentState, AgentStatus
from src.agent.workflow import run_knowledge_workflow


def completed_nodes(state: AgentState) -> list[str]:
    return [
        event["node"]
        for event in state.workflow_trace
        if event["event"] == "completed"
    ]


class LangGraphWorkflowTest(unittest.TestCase):
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

        state = run_langgraph_workflow(
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

    def test_insufficient_result_triggers_supplement_retrieval(self):
        calls = []

        def search_fn(query, top_k):
            calls.append(query)
            if len(calls) == 1:
                return [{"chunk_id": "c1", "content": "低相关", "score": 0.1}]
            return [{"chunk_id": "c2", "content": "高相关", "score": 0.9}]

        state = run_langgraph_workflow(
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
        state = run_langgraph_workflow(
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

        state = run_langgraph_workflow(
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

        state = run_langgraph_workflow(
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
        self.assertIn("总结生成失败", state.error)
        self.assertIn("DeepSeek 调用超时", state.error)
        failed_nodes = [
            event["node"]
            for event in state.workflow_trace
            if event["event"] == "failed"
        ]
        self.assertIn("summarize", failed_nodes)

    def test_langgraph_matches_handwritten_success_path(self):
        results = [{"chunk_id": "c1", "content": "相关资料", "score": 0.9}]
        overrides = {
            "analyze_intent": self.analyze,
            "search": lambda query, top_k: results,
            "generate_summary": lambda question, results: "同一份总结",
        }

        handwritten = run_knowledge_workflow(
            "查找 RAG 资料",
            model=object(),
            collection=object(),
            context_overrides=overrides,
        )
        langgraph = run_langgraph_workflow(
            "查找 RAG 资料",
            model=object(),
            collection=object(),
            context_overrides=overrides,
        )

        self.assertEqual(handwritten.status, langgraph.status)
        self.assertEqual(handwritten.answer, langgraph.answer)
        self.assertEqual(completed_nodes(handwritten), completed_nodes(langgraph))


if __name__ == "__main__":
    unittest.main()
