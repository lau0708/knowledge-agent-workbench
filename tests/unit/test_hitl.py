import unittest
from unittest.mock import patch

from src.agent.agent import run_agent
from src.agent.state import AgentStatus, ToolCallStatus
from src.hitl.models import (
    ConfirmationRequiredError,
    HitlConflictError,
    HitlExecutionError,
    PendingStatus,
)
from src.hitl.service import HitlService, should_confirm
from src.hitl.store import PendingOperationStore
from src.tools.registry import ToolRegistry


class HitlPolicyTest(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()
        self.registry.register(
            "read",
            "只读操作",
            {"type": "object", "properties": {}},
            lambda: {"ok": True},
        )
        self.registry.register(
            "delete",
            "删除操作",
            {
                "type": "object",
                "properties": {"document_id": {"type": "integer"}},
                "required": ["document_id"],
                "additionalProperties": False,
            },
            lambda document_id: {"deleted": document_id},
            risk_level="high",
        )
        self.registry.register(
            "forced",
            "强制确认操作",
            {"type": "object", "properties": {}},
            lambda: {"ok": True},
            risk_level="low",
            requires_confirmation=True,
        )

    def test_risk_level_and_forced_confirmation(self):
        self.assertFalse(should_confirm(self.registry.get("read")))
        self.assertTrue(should_confirm(self.registry.get("delete")))
        self.assertTrue(should_confirm(self.registry.get("forced")))


class HitlServiceTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.registry = ToolRegistry()
        self.registry.register(
            "echo",
            "普通工具",
            {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            lambda text: {"echo": text},
        )

        def delete_document(document_id):
            self.calls.append(document_id)
            return {"deleted": document_id}

        self.registry.register(
            "delete_document",
            "高风险删除工具",
            {
                "type": "object",
                "properties": {"document_id": {"type": "integer"}},
                "required": ["document_id"],
                "additionalProperties": False,
            },
            delete_document,
            risk_level="high",
        )

        self.service = HitlService()

    def test_low_risk_tool_executes_without_confirmation(self):
        result = self.service.dispatch(
            self.registry,
            "echo",
            {"text": "hi"},
            session_id="s1",
        )

        self.assertIn('"hi"', result)

    def test_high_risk_tool_creates_pending_operation(self):
        with self.assertRaises(ConfirmationRequiredError) as raised:
            self.service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 1},
                session_id="s1",
                tool_call_id="call_1",
            )

        operation = self.service.get_operation(raised.exception.operation_id)
        self.assertIsNotNone(operation)
        self.assertEqual(operation.status, PendingStatus.PENDING)
        self.assertEqual(operation.tool_call_id, "call_1")

    def test_approve_executes_and_prevents_duplicate(self):
        with self.assertRaises(ConfirmationRequiredError) as raised:
            self.service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 7},
                session_id="s1",
            )

        operation_id = raised.exception.operation_id
        operation = self.service.approve(operation_id, self.registry)

        self.assertEqual(operation.status, PendingStatus.EXECUTED)
        self.assertEqual(self.calls, [7])
        self.assertIn('"deleted": 7', operation.result)

        with self.assertRaises(HitlConflictError):
            self.service.approve(operation_id, self.registry)

    def test_reject_prevents_execution_and_duplicate(self):
        with self.assertRaises(ConfirmationRequiredError) as raised:
            self.service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 8},
                session_id="s1",
            )

        operation_id = raised.exception.operation_id
        operation = self.service.reject(operation_id, "用户不想删除")

        self.assertEqual(operation.status, PendingStatus.REJECTED)
        self.assertEqual(self.calls, [])
        self.assertIn("用户不想删除", operation.error)

        with self.assertRaises(HitlConflictError):
            self.service.reject(operation_id, "再次拒绝")

    def test_modify_then_approve_uses_modified_arguments(self):
        with self.assertRaises(ConfirmationRequiredError) as raised:
            self.service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 1},
                session_id="s1",
            )

        operation_id = raised.exception.operation_id
        self.service.modify(operation_id, {"document_id": 2})
        operation = self.service.approve(operation_id, self.registry)

        self.assertEqual(operation.status, PendingStatus.EXECUTED)
        self.assertEqual(self.calls, [2])

    def test_approve_revalidates_modified_arguments_and_does_not_execute(self):
        with self.assertRaises(ConfirmationRequiredError) as raised:
            self.service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 1},
                session_id="s1",
            )

        operation_id = raised.exception.operation_id

        with self.assertRaises(HitlExecutionError):
            self.service.approve(
                operation_id,
                self.registry,
                modified_arguments={"document_id": "not-an-integer"},
            )

        operation = self.service.get_operation(operation_id)
        self.assertEqual(self.calls, [])
        self.assertEqual(operation.status, PendingStatus.PENDING)

    def test_approve_rejects_tool_that_no_longer_requires_confirmation(self):
        with self.assertRaises(ConfirmationRequiredError) as raised:
            self.service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 1},
                session_id="s1",
            )

        downgraded_registry = ToolRegistry()
        downgraded_registry.register(
            "delete_document",
            "删除操作",
            {
                "type": "object",
                "properties": {"document_id": {"type": "integer"}},
                "required": ["document_id"],
                "additionalProperties": False,
            },
            lambda document_id: {"deleted": document_id},
            risk_level="low",
        )

        with self.assertRaises(HitlExecutionError):
            self.service.approve(
                raised.exception.operation_id,
                downgraded_registry,
            )

        self.assertEqual(self.calls, [])

    def test_expire_stale_marks_pending_as_expired(self):
        service = HitlService(store=PendingOperationStore(timeout_seconds=-1))

        with self.assertRaises(ConfirmationRequiredError) as raised:
            service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 3},
                session_id="s1",
            )

        expired = service.expire_stale()

        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].status, PendingStatus.EXPIRED)

    def test_expired_operation_cannot_be_approved(self):
        service = HitlService(store=PendingOperationStore(timeout_seconds=-1))

        with self.assertRaises(ConfirmationRequiredError) as raised:
            service.dispatch(
                self.registry,
                "delete_document",
                {"document_id": 4},
                session_id="s1",
            )

        operation_id = raised.exception.operation_id
        service.expire_stale()

        with self.assertRaises(HitlConflictError):
            service.approve(operation_id, self.registry)

        self.assertEqual(self.calls, [])


class AgentHitlIntegrationTest(unittest.TestCase):
    def test_agent_pauses_and_resumes_after_approval(self):
        registry = ToolRegistry()
        registry.register(
            "danger",
            "需要确认的操作",
            {
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            lambda value: {"done": value},
            risk_level="high",
        )

        responses = [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_danger",
                        "type": "function",
                        "function": {
                            "name": "danger",
                            "arguments": '{"value": 5}',
                        },
                    }
                ],
            },
            {"role": "assistant", "content": "已完成", "tool_calls": []},
        ]

        service = HitlService()

        with patch("src.agent.agent.build_default_registry", return_value=registry):
            with patch("src.agent.agent.chat_deepseek", side_effect=responses):
                state = run_agent(
                    "执行危险操作",
                    model=object(),
                    collection=object(),
                    confirmation_service=service,
                )

                self.assertEqual(state.status, AgentStatus.WAITING_CONFIRMATION)
                self.assertIsNotNone(state.pending_operation_id)
                self.assertEqual(
                    state.tool_calls[0].status,
                    ToolCallStatus.WAITING_CONFIRMATION,
                )

                operation = service.get_operation(state.pending_operation_id)
                approved = service.approve(
                    state.pending_operation_id,
                    registry,
                )

                state.add_message(
                    "tool",
                    approved.result or "",
                    tool_call_id=operation.tool_call_id,
                )
                state.resolve_tool_call(
                    tool_call_id=operation.tool_call_id,
                    status=ToolCallStatus.SUCCESS,
                    result=approved.result or "",
                )
                state.pending_operation_id = None

                resumed = run_agent(
                    question=state.user_input,
                    model=object(),
                    collection=object(),
                    state=state,
                    confirmation_service=service,
                    resume=True,
                )

        self.assertEqual(resumed.status, AgentStatus.COMPLETED)
        self.assertEqual(resumed.answer, "已完成")
        self.assertEqual(resumed.tool_call_count, 1)


if __name__ == "__main__":
    unittest.main()
