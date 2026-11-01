import tempfile
import unittest
from pathlib import Path

from src.agent.state import AgentState
from src.database import db
from src.hitl.store import PendingOperationStore
from src.memory import memory_store
from src.memory.models import MemoryRecord
from src.observability.tracing import TraceStore, build_trace


class PersistenceBoundaryTest(unittest.TestCase):
    def test_memory_persists_across_new_store_connections(self):
        tempdir = tempfile.TemporaryDirectory()
        old_db_path = db.DB_PATH

        try:
            db.DB_PATH = Path(tempdir.name) / "memory.db"
            memory_store.init_memory_table()

            memory_store.save_memory(
                MemoryRecord(
                    owner_id="owner-1",
                    memory_key="topic",
                    content="长期记忆应跨连接保留",
                )
            )

            self.assertEqual(
                [item.content for item in memory_store.list_memories("owner-1")],
                ["长期记忆应跨连接保留"],
            )
        finally:
            db.DB_PATH = old_db_path
            tempdir.cleanup()

    def test_trace_store_is_process_local(self):
        first_store = TraceStore()
        state = AgentState.create("查询 RAG", session_id="s1")
        state.mark_completed("回答")
        first_store.add(build_trace(state))

        second_store = TraceStore()

        self.assertEqual(len(first_store.list()), 1)
        self.assertEqual(second_store.list(), [])

    def test_hitl_pending_store_is_process_local(self):
        first_store = PendingOperationStore()
        operation = first_store.create(
            operation_id="op-1",
            session_id="s1",
            tool_name="delete_document",
            arguments={"document_id": 1},
        )

        second_store = PendingOperationStore()

        self.assertEqual(first_store.get("op-1").operation_id, operation.operation_id)
        self.assertIsNone(second_store.get("op-1"))


if __name__ == "__main__":
    unittest.main()
