import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.database import db
from src.memory.memory_extractor import extract_memory_candidates
from src.memory.memory_retriever import retrieve_relevant_memories
from src.memory.memory_service import MemoryService
from src.memory.memory_store import (
    delete_expired_memories,
    delete_memory,
    get_memory,
    init_memory_table,
    list_memories,
    save_memory,
    search_memories,
    update_memory,
)
from src.memory.models import MemoryRecord
from src.memory.short_term import trim_messages


class ShortTermMemoryTest(unittest.TestCase):
    def test_trim_keeps_system_and_recent_turn(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "first-answer"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "second-answer"},
        ]

        trimmed = trim_messages(messages, max_messages=4)

        self.assertEqual(
            [message["role"] for message in trimmed],
            ["system", "user", "assistant"],
        )
        self.assertEqual(trimmed[0]["content"], "system")
        self.assertEqual(trimmed[-1]["content"], "second-answer")

    def test_trim_returns_original_when_under_limit(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "question"},
        ]

        self.assertEqual(trim_messages(messages, max_messages=10), messages)


class MemoryStoreTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / "memory.db"
        init_memory_table()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    def make_record(self, **kwargs) -> MemoryRecord:
        defaults = {
            "memory_key": "pref_python",
            "content": "用户喜欢 Python",
            "owner_id": "user-1",
            "source": "conversation",
            "importance": 0.8,
        }
        defaults.update(kwargs)
        return MemoryRecord(**defaults)

    def test_save_get_update_delete(self):
        saved = save_memory(self.make_record())

        self.assertIsNotNone(saved.id)
        fetched = get_memory(saved.id)
        self.assertEqual(fetched.content, "用户喜欢 Python")

        updated = update_memory(saved.id, content="用户喜欢 Python 和 FastAPI")
        self.assertEqual(updated.content, "用户喜欢 Python 和 FastAPI")

        self.assertTrue(delete_memory(saved.id))
        self.assertIsNone(get_memory(saved.id))

    def test_upsert_conflict_updates_existing_record(self):
        save_memory(self.make_record())
        save_memory(self.make_record(content="用户更喜欢 FastAPI"))

        records = list_memories(owner_id="user-1")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].content, "用户更喜欢 FastAPI")

    def test_search_and_owner_isolation(self):
        save_memory(self.make_record())
        save_memory(
            self.make_record(
                memory_key="pref_coffee",
                content="用户喜欢咖啡",
                owner_id="user-2",
            )
        )

        python_records = search_memories(tokens=["python"], owner_id="user-1")
        user2_records = search_memories(tokens=["咖啡"], owner_id="user-2")

        self.assertEqual(len(python_records), 1)
        self.assertEqual(python_records[0].owner_id, "user-1")
        self.assertEqual(len(user2_records), 1)
        self.assertEqual(user2_records[0].content, "用户喜欢咖啡")

    def test_expired_memory_is_excluded_and_removed(self):
        expired_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        save_memory(self.make_record(expires_at=expired_at))
        save_memory(
            self.make_record(
                memory_key="pref_rag",
                content="用户在学习 RAG",
            )
        )

        active_records = list_memories(owner_id="user-1")
        self.assertEqual([record.memory_key for record in active_records], ["pref_rag"])

        all_records = list_memories(owner_id="user-1", include_expired=True)
        self.assertEqual(len(all_records), 2)

        deleted = delete_expired_memories()
        self.assertEqual(deleted, 1)

    def test_database_write_failure_propagates(self):
        with patch("src.memory.memory_store.init_memory_table"), patch(
            "src.memory.memory_store.db.get_connection",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                save_memory(self.make_record())


class MemoryRetrieverAndExtractorTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / "memory.db"
        init_memory_table()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    def test_retrieve_returns_relevant_memory_not_all(self):
        save_memory(
            MemoryRecord(
                memory_key="pref_python",
                content="用户正在学习 Python",
                owner_id="user-1",
            )
        )
        save_memory(
            MemoryRecord(
                memory_key="pref_coffee",
                content="用户喜欢咖啡",
                owner_id="user-1",
            )
        )

        memories = retrieve_relevant_memories("Python 学习", owner_id="user-1")

        self.assertEqual(len(memories), 1)
        self.assertIn("Python", memories[0]["content"])

    def test_extractor_saves_positive_and_skips_transient(self):
        saved = extract_memory_candidates("我喜欢 Python", "用户喜欢 Python")
        skipped = extract_memory_candidates("什么是 Python", "Python 是编程语言")

        self.assertEqual(saved[0].action, "save")
        self.assertEqual(saved[0].content, "用户喜欢 Python")
        self.assertEqual(skipped, [])

    def test_extractor_creates_forget_candidate(self):
        candidates = extract_memory_candidates("不要记住我喜欢 Python", "")

        self.assertEqual(candidates[0].action, "forget")


class MemoryServiceTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.tempdir.name) / "memory.db"
        self.service = MemoryService(short_term_max_messages=10)
        self.service.init()

    def tearDown(self):
        db.DB_PATH = self.old_db_path
        self.tempdir.cleanup()

    def test_remember_and_reuse_in_new_context(self):
        self.service.remember_turn(
            "记住我喜欢 Python",
            "用户喜欢 Python",
            owner_id="user-1",
            session_id="session-1",
        )

        context = self.service.build_context_block(
            "Python",
            owner_id="user-1",
        )

        self.assertIn("用户喜欢 Python", context)

    def test_forget_turn_removes_related_memory(self):
        self.service.remember_turn(
            "记住我喜欢 Python",
            "用户喜欢 Python",
            owner_id="user-1",
            session_id="session-1",
        )

        self.service.remember_turn(
            "不要记住我喜欢 Python",
            "",
            owner_id="user-1",
            session_id="session-1",
        )

        self.assertEqual(
            self.service.retrieve_relevant("Python", owner_id="user-1"),
            [],
        )


if __name__ == "__main__":
    unittest.main()
