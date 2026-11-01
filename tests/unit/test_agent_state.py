import unittest

from src.agent.session import AgentSessionManager
from src.agent.state import AgentState, AgentStatus, ToolCallStatus


class AgentStateTest(unittest.TestCase):
    def test_create_uses_defaults(self):
        state = AgentState.create("查询知识库")

        self.assertTrue(state.session_id)
        self.assertEqual(state.user_input, "查询知识库")
        self.assertEqual(state.status, AgentStatus.PENDING)
        self.assertEqual(state.messages, [])
        self.assertEqual(state.tool_calls, [])
        self.assertEqual(state.tool_results, [])
        self.assertEqual(state.tool_call_count, 0)
        self.assertIsNone(state.error)
        self.assertIsNone(state.answer)
        self.assertTrue(state.created_at)
        self.assertTrue(state.updated_at)

    def test_create_accepts_explicit_session_id(self):
        state = AgentState.create("查询知识库", session_id="session-1")

        self.assertEqual(state.session_id, "session-1")

    def test_lifecycle_transitions(self):
        state = AgentState.create("查询知识库")
        state.start()
        self.assertEqual(state.status, AgentStatus.RUNNING)

        state.mark_completed("回答")
        self.assertEqual(state.status, AgentStatus.COMPLETED)
        self.assertEqual(state.answer, "回答")
        self.assertIsNone(state.error)

        failed_state = AgentState.create("触发失败")
        failed_state.mark_failed("模型调用失败")
        self.assertEqual(failed_state.status, AgentStatus.FAILED)
        self.assertEqual(failed_state.error, "模型调用失败")

    def test_messages_keep_order_and_tool_call_id(self):
        state = AgentState.create("用工具")

        state.add_message("system", "你是助手")
        state.add_message("user", "你好")
        state.add_message(
            "assistant",
            None,
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "echo", "arguments": "{}"},
                }
            ],
        )
        state.add_message("tool", "执行成功", tool_call_id="call_1")

        self.assertEqual(
            [message["role"] for message in state.messages],
            ["system", "user", "assistant", "tool"],
        )
        self.assertEqual(state.messages[2]["tool_calls"][0]["id"], "call_1")
        self.assertEqual(state.messages[3]["tool_call_id"], "call_1")

    def test_add_tool_call_records_result_and_status(self):
        state = AgentState.create("调用工具")

        state.add_tool_call(
            name="search_knowledge_base",
            arguments={"query": "RAG"},
            result='{"count": 1}',
            status=ToolCallStatus.SUCCESS,
            tool_call_id="call_search",
        )
        state.add_tool_call(
            name="not_exists",
            arguments={},
            result='{"error": "未注册"}',
            status=ToolCallStatus.FAILED,
            error="未注册",
            tool_call_id="call_missing",
        )

        self.assertEqual(state.tool_call_count, 2)
        self.assertEqual(len(state.tool_calls), 2)
        self.assertEqual(len(state.tool_results), 2)

        self.assertEqual(state.tool_calls[0].name, "search_knowledge_base")
        self.assertEqual(state.tool_calls[0].status, ToolCallStatus.SUCCESS)
        self.assertIsNone(state.tool_calls[0].error)

        self.assertEqual(state.tool_calls[1].status, ToolCallStatus.FAILED)
        self.assertEqual(state.tool_calls[1].error, "未注册")
        self.assertEqual(state.tool_results[1]["tool_call_id"], "call_missing")

    def test_to_dict_serializes_enums(self):
        state = AgentState.create("查询知识库", session_id="session-1")
        state.start()
        state.mark_completed("回答")

        payload = state.to_dict()

        self.assertEqual(payload["session_id"], "session-1")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["answer"], "回答")
        self.assertEqual(payload["tool_call_count"], 0)
        self.assertIn("created_at", payload)
        self.assertIn("updated_at", payload)


class AgentSessionManagerTest(unittest.TestCase):
    def test_create_get_and_remove_session(self):
        manager = AgentSessionManager()

        state = manager.create("第一轮问题", session_id="session-a")

        self.assertIs(manager.get("session-a"), state)
        self.assertEqual(manager.list_sessions(), ["session-a"])

        removed = manager.remove("session-a")
        self.assertIs(removed, state)
        self.assertIsNone(manager.get("session-a"))
        self.assertEqual(manager.list_sessions(), [])

    def test_sessions_do_not_pollute_each_other(self):
        manager = AgentSessionManager()

        session_a = manager.create("问题 A", session_id="session-a")
        session_b = manager.create("问题 B", session_id="session-b")

        session_a.start()
        session_a.add_message("user", "只有 A 的消息")
        session_a.add_tool_call(
            name="echo",
            arguments={"text": "A"},
            result='{"echo": "A"}',
            status=ToolCallStatus.SUCCESS,
            tool_call_id="call-a",
        )

        self.assertEqual(session_b.status, AgentStatus.PENDING)
        self.assertEqual(session_b.messages, [])
        self.assertEqual(session_b.tool_calls, [])
        self.assertEqual(session_b.tool_call_count, 0)
        self.assertEqual(manager.list_sessions(), ["session-a", "session-b"])


if __name__ == "__main__":
    unittest.main()
