import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import chromadb
from fastapi.testclient import TestClient

from src import main
from src.agent.session import AgentSessionManager
from src.agent.state import AgentState
from src.database import db
from src.services import document_service
from src.services.indexing_service import sync_document_chunks
from src.tools.registry import ToolRegistry


def fake_sync_file(collection, source, chunk_size=None, chunk_overlap=None):
    content = Path(source).read_text(encoding="utf-8")
    return sync_document_chunks(
        collection,
        source,
        [
            {
                "chunk_id": f"{Path(source).stem}_0",
                "source": source,
                "chunk_index": 0,
                "content": content[:20],
                "embedding": [0.1] * 8,
            }
        ],
    )


class DocumentApiTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self._old_db_path = db.DB_PATH
        self._old_docs_dir = document_service.DOCUMENTS_DIR
        self._old_load_model = main.load_embedding_model
        self._old_get_collection = main.get_collection

        db.DB_PATH = Path(self.tempdir.name) / "test.db"
        db.init_db()
        document_service.DOCUMENTS_DIR = Path(self.tempdir.name) / "docs"

        self.client = chromadb.EphemeralClient()
        self.collection = self.client.get_or_create_collection(
            name=f"api_test_{uuid.uuid4().hex}",
            metadata={"hnsw:space": "cosine"},
        )

        main.load_embedding_model = lambda: object()
        main.get_collection = lambda: self.collection

    def tearDown(self):
        main.get_collection = self._old_get_collection
        main.load_embedding_model = self._old_load_model
        document_service.DOCUMENTS_DIR = self._old_docs_dir
        db.DB_PATH = self._old_db_path
        self.tempdir.cleanup()

    def test_document_lifecycle_and_errors(self):
        with patch.object(document_service, "sync_file", side_effect=fake_sync_file):
            with TestClient(main.app) as client:
                upload = client.post(
                    "/documents",
                    files={"file": ("note.md", b"# hello world", "text/markdown")},
                )
                self.assertEqual(upload.status_code, 201, upload.text)
                document_id = upload.json()["id"]

                self.assertEqual(len(client.get("/documents").json()), 1)
                self.assertEqual(len(client.get(f"/documents/{document_id}").json()["chunks"]), 1)

                update = client.put(
                    f"/documents/{document_id}",
                    json={"content": "# updated content"},
                )
                self.assertEqual(update.status_code, 200, update.text)

                delete = client.delete(f"/documents/{document_id}")
                self.assertEqual(delete.status_code, 200, delete.text)
                self.assertTrue(delete.json()["deleted"])

    def test_unified_error_responses(self):
        with patch.object(document_service, "sync_file", side_effect=fake_sync_file):
            with TestClient(main.app) as client:
                upload = client.post(
                    "/documents",
                    files={"file": ("note.md", b"# hello", "text/markdown")},
                )
                document_id = upload.json()["id"]

                duplicate = client.post(
                    "/documents",
                    files={"file": ("note.md", b"dup", "text/markdown")},
                )
                self.assertEqual(duplicate.status_code, 409)
                self.assertEqual(duplicate.json()["error"]["code"], "DUPLICATE_DOCUMENT")

                unsupported = client.post(
                    "/documents",
                    files={"file": ("note.txt", b"txt", "text/plain")},
                )
                self.assertEqual(unsupported.status_code, 400)
                self.assertEqual(unsupported.json()["error"]["code"], "UNSUPPORTED_DOCUMENT_TYPE")

                missing = client.get("/documents/999999")
                self.assertEqual(missing.status_code, 404)
                self.assertEqual(missing.json()["error"]["code"], "DOCUMENT_NOT_FOUND")

                invalid = client.post("/documents")
                self.assertEqual(invalid.status_code, 422)
                self.assertEqual(invalid.json()["error"]["code"], "VALIDATION_ERROR")

    def test_unexpected_exception_does_not_leak_internal_details(self):
        with patch.object(
            main,
            "ask",
            side_effect=RuntimeError("internal secret sk-test-123"),
        ):
            with TestClient(main.app, raise_server_exceptions=False) as client:
                response = client.post(
                    "/chat",
                    json={"question": "你好"},
                )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_ERROR")
        self.assertNotIn("sk-test-123", response.text)

    def test_hitl_execution_error_does_not_leak_internal_details(self):
        operation_id = uuid.uuid4().hex[:12]
        main.hitl_service.store.create(
            operation_id=operation_id,
            session_id="leak-session",
            tool_name="danger",
            arguments={},
        )

        registry = ToolRegistry()
        registry.register(
            "danger",
            "危险操作",
            {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            lambda: (_ for _ in ()).throw(
                RuntimeError("internal secret sk-test-123")
            ),
            risk_level="high",
        )

        with patch.object(main, "build_default_registry", return_value=registry):
            with TestClient(main.app, raise_server_exceptions=False) as client:
                response = client.post(
                    f"/agent/confirmations/{operation_id}/approve",
                    json={},
                )

        self.assertEqual(response.status_code, 422)
        self.assertNotIn("sk-test-123", response.text)
        self.assertIn("工具执行失败", response.text)

    def test_agent_chat_reuses_existing_session_state(self):
        with patch.object(main, "agent_session_manager", AgentSessionManager()):
            with patch("src.main.run_agent") as run_agent_mock:

                def fake_run(
                    question,
                    model,
                    collection,
                    state=None,
                    session_id=None,
                    memory_context=None,
                    confirmation_service=None,
                    resume=False,
                ):
                    if state is None:
                        state = AgentState.create(question, session_id=session_id)
                    else:
                        state.user_input = question

                    state.add_message("user", question)
                    state.add_message("assistant", f"{question}-answer")
                    state.mark_completed(f"{question}-answer")
                    return state

                run_agent_mock.side_effect = fake_run

                with TestClient(main.app) as client:
                    first = client.post(
                        "/agent/chat",
                        json={"question": "第一轮", "session_id": "s1"},
                    )
                    second = client.post(
                        "/agent/chat",
                        json={"question": "第二轮", "session_id": "s1"},
                    )
                    other = client.post(
                        "/agent/chat",
                        json={"question": "其他会话", "session_id": "s2"},
                    )

                self.assertEqual(first.status_code, 200, first.text)
                self.assertEqual(second.status_code, 200, second.text)
                self.assertEqual(other.status_code, 200, other.text)
                self.assertEqual(run_agent_mock.call_count, 3)

                self.assertIsNone(run_agent_mock.call_args_list[0].kwargs["state"])
                self.assertIsNotNone(run_agent_mock.call_args_list[1].kwargs["state"])
                self.assertEqual(
                    run_agent_mock.call_args_list[1].kwargs["state"].session_id,
                    "s1",
                )
                self.assertEqual(
                    run_agent_mock.call_args_list[2].kwargs["session_id"],
                    "s2",
                )

                saved_s1 = main.agent_session_manager.get("s1")
                saved_s2 = main.agent_session_manager.get("s2")
                self.assertEqual(saved_s1.answer, "第二轮-answer")
                self.assertEqual(saved_s2.answer, "其他会话-answer")
                self.assertEqual(
                    [message["role"] for message in saved_s1.messages],
                    ["user", "assistant", "user", "assistant"],
                )

    def test_agent_trace_endpoints(self):
        store = main.TraceStore()

        with patch.object(main, "agent_session_manager", AgentSessionManager()):
            with patch.object(main, "trace_store", store):
                with patch("src.main.run_agent") as run_agent_mock:

                    def fake_run(
                        question,
                        model,
                        collection,
                        state=None,
                        session_id=None,
                        memory_context=None,
                        confirmation_service=None,
                        resume=False,
                    ):
                        state = state or AgentState.create(question, session_id=session_id)
                        state.user_input = question
                        state.mark_completed(f"{question}-answer")
                        return state

                    run_agent_mock.side_effect = fake_run

                    with TestClient(main.app) as client:
                        response = client.post(
                            "/agent/chat",
                            json={"question": "追踪我", "session_id": "trace-s1"},
                        )

                    self.assertEqual(response.status_code, 200, response.text)
                    traces = store.list("trace-s1")
                    self.assertEqual(len(traces), 1)
                    trace_id = traces[0].trace_id

                    with TestClient(main.app) as client:
                        listing = client.get(
                            "/agent/traces",
                            params={"session_id": "trace-s1"},
                        )
                        detail = client.get(f"/agent/traces/{trace_id}")
                        analysis = client.get(
                            f"/agent/traces/{trace_id}/analysis"
                        )

                    self.assertEqual(listing.status_code, 200)
                    self.assertEqual(len(listing.json()), 1)
                    self.assertEqual(listing.json()[0]["trace_id"], trace_id)
                    self.assertEqual(detail.status_code, 200)
                    self.assertEqual(detail.json()["status"], "completed")
                    self.assertEqual(analysis.status_code, 200)
                    self.assertEqual(analysis.json()["failure_stage"], "none")

    def test_confirmation_endpoints(self):
        class FakeOperation:
            def __init__(self, operation_id="op1", status="pending"):
                self.operation_id = operation_id
                self.session_id = "missing-session"
                self.tool_name = "delete_document"
                self.arguments = {"document_id": 1}
                self.tool_call_id = "call_1"
                self.status = status
                self.result = None
                self.error = None

            def to_dict(self):
                return {
                    "operation_id": self.operation_id,
                    "session_id": self.session_id,
                    "tool_name": self.tool_name,
                    "arguments": self.arguments,
                    "tool_call_id": self.tool_call_id,
                    "status": self.status,
                    "result": self.result,
                    "error": self.error,
                }

        class FakeHitlService:
            def list_operations(self, session_id=None):
                return [FakeOperation()]

            def get_operation(self, operation_id):
                return FakeOperation(operation_id)

            def modify(self, operation_id, arguments):
                return FakeOperation(operation_id, "pending")

            def approve(self, operation_id, registry, modified_arguments=None):
                operation = FakeOperation(operation_id, "executed")
                operation.result = '{"deleted": 1}'
                return operation

            def reject(self, operation_id, reason=None):
                operation = FakeOperation(operation_id, "rejected")
                operation.error = reason or "用户拒绝执行"
                return operation

        with patch.object(main, "hitl_service", FakeHitlService()):
            with TestClient(main.app) as client:
                listing = client.get("/agent/confirmations", params={"session_id": "s1"})
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(listing.json()[0]["operation_id"], "op1")

                detail = client.get("/agent/confirmations/op1")
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()["tool_name"], "delete_document")

                modify = client.post(
                    "/agent/confirmations/op1/modify",
                    json={"arguments": {"document_id": 2}},
                )
                self.assertEqual(modify.status_code, 200)

                approve = client.post(
                    "/agent/confirmations/op1/approve",
                    json={"arguments": {"document_id": 2}},
                )
                self.assertEqual(approve.status_code, 200)
                self.assertEqual(approve.json()["operation"]["status"], "executed")

                reject = client.post(
                    "/agent/confirmations/op1/reject",
                    json={"reason": "不需要删除"},
                )
                self.assertEqual(reject.status_code, 200)
                self.assertEqual(reject.json()["operation"]["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
