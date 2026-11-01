import unittest
from unittest.mock import patch

import requests

from src.rag.llm import chat_deepseek


class LlmErrorHandlingTest(unittest.TestCase):
    def test_missing_api_key_raises_clear_error(self):
        with patch("src.rag.llm.settings.deepseek_api_key", ""):
            with self.assertRaises(RuntimeError) as raised:
                chat_deepseek([{"role": "user", "content": "你好"}])

        self.assertIn("DEEPSEEK_API_KEY", str(raised.exception))

    def test_timeout_propagates_without_leaking_api_key(self):
        with patch("src.rag.llm.settings.deepseek_api_key", "sk-test-secret"), patch(
            "src.rag.llm.requests.post",
            side_effect=requests.exceptions.Timeout("请求超时"),
        ):
            with self.assertRaises(requests.exceptions.Timeout) as raised:
                chat_deepseek([{"role": "user", "content": "你好"}])

        self.assertNotIn("sk-test-secret", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
