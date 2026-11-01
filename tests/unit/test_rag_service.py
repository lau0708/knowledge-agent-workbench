import unittest
from unittest.mock import patch

from src.services.rag_service import ask


class RagServiceEdgeTest(unittest.TestCase):
    def test_no_results_returns_safe_answer_without_calling_llm(self):
        with patch("src.services.rag_service.search", return_value=[]) as search_mock, patch(
            "src.services.rag_service.call_deepseek"
        ) as llm_mock, patch(
            "src.services.rag_service.evaluate_generation"
        ) as eval_mock:
            result = ask("什么是 RAG？", object(), object())

        self.assertEqual(result["context"], [])
        self.assertEqual(result["evaluation"], None)
        self.assertIn("暂时无法回答", result["answer"])
        search_mock.assert_called_once()
        llm_mock.assert_not_called()
        eval_mock.assert_not_called()

    def test_low_score_does_not_generate_unreliable_answer(self):
        low_result = [
            {
                "chunk_id": "x_0",
                "source": "rag-intro.md",
                "content": "RAG 是检索增强生成。",
                "score": 0.3,
            }
        ]

        with patch("src.services.rag_service.search", return_value=low_result), patch(
            "src.services.rag_service.call_deepseek"
        ) as llm_mock:
            result = ask("什么是 RAG？", object(), object())

        self.assertEqual(result["context"], [])
        self.assertIn("暂时无法回答", result["answer"])
        llm_mock.assert_not_called()

    def test_llm_failure_propagates_instead_of_silently_returning_answer(self):
        good_result = [
            {
                "chunk_id": "x_0",
                "source": "rag-intro.md",
                "content": "RAG 是检索增强生成。",
                "score": 0.9,
            }
        ]

        with patch("src.services.rag_service.search", return_value=good_result), patch(
            "src.services.rag_service.call_deepseek",
            side_effect=RuntimeError("DeepSeek 调用超时"),
        ):
            with self.assertRaises(RuntimeError):
                ask("什么是 RAG？", object(), object())


if __name__ == "__main__":
    unittest.main()
