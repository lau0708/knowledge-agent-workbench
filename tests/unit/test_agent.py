import unittest
from unittest.mock import patch

from src.agent.agent import run_agent
from src.agent.state import AgentStatus, ToolCallStatus
from src.tools.registry import ToolRegistry


class AgentLoopTest(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(
            name="echo",
            description="回显",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=lambda text: {"echo": text},
        )

    def test_direct_answer_without_tool(self):
        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch(
                "src.agent.agent.chat_deepseek",
                return_value={"role": "assistant", "content": "你好", "tool_calls": []},
            ):
                result = run_agent("你好", model=object(), collection=object())

        self.assertEqual(result.status, AgentStatus.COMPLETED)
        self.assertEqual(result.answer, "你好")
        self.assertEqual(result.tool_call_count, 0)

    def test_memory_context_is_injected_into_system_prompt(self):
        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch(
                "src.agent.agent.chat_deepseek",
                return_value={"role": "assistant", "content": "你好", "tool_calls": []},
            ):
                result = run_agent(
                    "你好",
                    model=object(),
                    collection=object(),
                    memory_context="[长期记忆]\n- 用户喜欢 Python",
                )

        self.assertEqual(result.messages[0]["role"], "system")
        self.assertIn("用户喜欢 Python", result.messages[0]["content"])

    def test_tool_call_round_trip(self):
        responses = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "echo",
                            "arguments": '{"text": "hi"}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "已完成", "tool_calls": []},
        ]

        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch("src.agent.agent.chat_deepseek", side_effect=responses):
                result = run_agent("echo hi", model=object(), collection=object())

        self.assertEqual(result.status, AgentStatus.COMPLETED)
        self.assertEqual(result.answer, "已完成")
        self.assertEqual(result.tool_call_count, 1)
        self.assertEqual(result.tool_calls[0].name, "echo")
        self.assertEqual(result.tool_calls[0].status, ToolCallStatus.SUCCESS)
        self.assertIn('"echo": "hi"', result.tool_calls[0].result)

    def test_max_tool_calls_limits_loop(self):
        response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_loop",
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "arguments": '{"text": "loop"}',
                    },
                }
            ],
        }

        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch("src.agent.agent.chat_deepseek", return_value=response):
                result = run_agent(
                    "loop",
                    model=object(),
                    collection=object(),
                    max_tool_calls=2,
                )

        self.assertEqual(result.status, AgentStatus.FAILED)
        self.assertEqual(result.tool_call_count, 2)
        self.assertIn("最大工具调用轮数", result.error)

    def test_model_call_failure_marks_state_failed(self):
        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch(
                "src.agent.agent.chat_deepseek",
                side_effect=RuntimeError("网络错误"),
            ):
                result = run_agent("查询知识库", model=object(), collection=object())

        self.assertEqual(result.status, AgentStatus.FAILED)
        self.assertIn("模型调用失败", result.error)
        self.assertIn("网络错误", result.error)

    def test_unregistered_tool_is_reported_to_model(self):
        response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_unknown",
                    "type": "function",
                    "function": {
                        "name": "not_exists",
                        "arguments": "{}",
                    },
                }
            ],
        }

        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch(
                "src.agent.agent.chat_deepseek",
                side_effect=[
                    response,
                    {"role": "assistant", "content": "无法执行", "tool_calls": []},
                ],
            ):
                result = run_agent("unknown", model=object(), collection=object())

        self.assertEqual(result.status, AgentStatus.COMPLETED)
        self.assertEqual(result.answer, "无法执行")
        self.assertEqual(result.tool_calls[0].status, ToolCallStatus.FAILED)
        self.assertIn("未注册的工具", result.tool_calls[0].error)

    def test_existing_state_is_reused_for_conversation(self):
        from src.agent.state import AgentState

        state = AgentState.create("第一轮", session_id="session-1")

        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch(
                "src.agent.agent.chat_deepseek",
                return_value={"role": "assistant", "content": "第一答", "tool_calls": []},
            ):
                first = run_agent("第一轮", model=object(), collection=object(), state=state)

        with patch("src.agent.agent.build_default_registry", return_value=self.registry):
            with patch(
                "src.agent.agent.chat_deepseek",
                return_value={"role": "assistant", "content": "第二答", "tool_calls": []},
            ):
                second = run_agent("第二轮", model=object(), collection=object(), state=first)

        self.assertIs(second, state)
        self.assertEqual(second.session_id, "session-1")
        self.assertEqual(second.status, AgentStatus.COMPLETED)
        self.assertEqual(second.answer, "第二答")
        self.assertEqual(
            [message["role"] for message in second.messages],
            ["system", "user", "assistant", "user", "assistant"],
        )
        self.assertEqual(second.messages[1]["content"], "第一轮")
        self.assertEqual(second.messages[3]["content"], "第二轮")


if __name__ == "__main__":
    unittest.main()
