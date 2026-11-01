import argparse
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import chromadb

from src.database import db
from src.logging_config import setup_logging
from src.rag.vector_store import get_chunks_by_source
from src.services.indexing_service import (
    StorageSyncError,
    delete_document_sync,
    prune_missing_documents,
    sync_document_chunks,
    verify_consistency,
)


def make_chunks(source: str, count: int, embedding_dim: int = 8) -> list[dict]:
    """构造不依赖 Embedding 模型的测试 Chunk。"""

    return [
        {
            "chunk_id": f"{Path(source).stem}_{index}",
            "source": source,
            "chunk_index": index,
            "content": f"测试内容 {index}",
            "embedding": [0.1 * (index + 1)] * embedding_dim,
        }
        for index in range(count)
    ]


class IndexingServiceTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self._old_db_path = db.DB_PATH

        db.DB_PATH = Path(self.tempdir.name) / "test.db"
        db.init_db()

        self.client = chromadb.EphemeralClient()
        self.collection_name = f"test_knowledge_base_{uuid.uuid4().hex}"
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def tearDown(self):
        db.DB_PATH = self._old_db_path
        self.tempdir.cleanup()

    def _sqlite_chunks(self, source: str) -> list[tuple[str, str]]:
        snapshot = db.get_document_chunks(source)

        if snapshot is None:
            return []

        return sorted(
            (chunk["chunk_id"], chunk["content"])
            for chunk in snapshot["chunks"]
        )

    def _chroma_chunks(self, source: str) -> list[tuple[str, str]]:
        return sorted(
            (record["id"], record["document"])
            for record in get_chunks_by_source(self.collection, source)
        )

    def test_sync_new_document(self):
        source = "data/documents/test-sync.md"
        chunks = make_chunks(source, 3)

        synced = sync_document_chunks(self.collection, source, chunks)

        expected = sorted((chunk["chunk_id"], chunk["content"]) for chunk in chunks)

        self.assertEqual(synced, 3)
        self.assertEqual(self._sqlite_chunks(source), expected)
        self.assertEqual(self._chroma_chunks(source), expected)
        self.assertTrue(verify_consistency(self.collection)["is_consistent"])

    def test_sync_is_idempotent(self):
        source = "data/documents/test-idempotent.md"
        chunks = make_chunks(source, 2)

        sync_document_chunks(self.collection, source, chunks)
        sync_document_chunks(self.collection, source, chunks)

        self.assertEqual(self.collection.count(), 2)
        self.assertEqual(self._sqlite_chunks(source), self._chroma_chunks(source))
        self.assertTrue(verify_consistency(self.collection)["is_consistent"])

    def test_update_document_syncs_both_sides(self):
        source = "data/documents/test-update.md"
        chunks_v1 = make_chunks(source, 2)

        sync_document_chunks(self.collection, source, chunks_v1)

        chunks_v2 = [
            {
                "chunk_id": chunks_v1[0]["chunk_id"],
                "source": source,
                "chunk_index": 0,
                "content": "更新后的内容 0",
                "embedding": [0.2] * 8,
            },
            {
                "chunk_id": f"{Path(source).stem}_2",
                "source": source,
                "chunk_index": 2,
                "content": "新增的内容 2",
                "embedding": [0.3] * 8,
            },
        ]

        sync_document_chunks(self.collection, source, chunks_v2)

        expected = sorted(
            (chunk["chunk_id"], chunk["content"])
            for chunk in chunks_v2
        )

        self.assertEqual(self._sqlite_chunks(source), expected)
        self.assertEqual(self._chroma_chunks(source), expected)
        self.assertNotIn(chunks_v1[1]["chunk_id"], {chunk_id for chunk_id, _ in expected})
        self.assertTrue(verify_consistency(self.collection)["is_consistent"])

    def test_delete_document_syncs_both_sides(self):
        source = "data/documents/test-delete.md"
        chunks = make_chunks(source, 2)

        sync_document_chunks(self.collection, source, chunks)
        delete_document_sync(self.collection, source)

        self.assertIsNone(db.get_document_chunks(source))
        self.assertEqual(self._chroma_chunks(source), [])
        self.assertTrue(verify_consistency(self.collection)["is_consistent"])

    def test_chroma_failure_rolls_back_sqlite(self):
        source = "data/documents/test-rollback.md"
        chunks = make_chunks(source, 2)

        with patch(
            "src.services.indexing_service.add_chunks",
            side_effect=RuntimeError("chroma down"),
        ):
            with self.assertRaises(StorageSyncError):
                sync_document_chunks(self.collection, source, chunks)

        self.assertIsNone(db.get_document_chunks(source))
        self.assertEqual(self._chroma_chunks(source), [])

    def test_sqlite_failure_does_not_touch_chroma(self):
        source = "data/documents/test-sqlite-failure.md"
        chunks = make_chunks(source, 2)

        with patch(
            "src.services.indexing_service.replace_document_chunks",
            side_effect=RuntimeError("sqlite down"),
        ):
            with self.assertRaises(StorageSyncError):
                sync_document_chunks(self.collection, source, chunks)

        self.assertIsNone(db.get_document_chunks(source))
        self.assertEqual(self._chroma_chunks(source), [])

    def test_consistency_detects_missing_chroma_document(self):
        source = "data/documents/test-consistency.md"
        chunks = make_chunks(source, 2)

        sync_document_chunks(self.collection, source, chunks)
        self.collection.delete(where={"source": source})

        report = verify_consistency(self.collection)

        self.assertFalse(report["is_consistent"])
        self.assertEqual(report["only_sqlite"], [source])

    def test_prune_limited_to_managed_directory(self):
        managed_dir = Path(self.tempdir.name) / "managed"
        other_dir = Path(self.tempdir.name) / "other"

        inside_source = str(managed_dir / "removed.md")
        outside_source = str(other_dir / "keep.md")

        sync_document_chunks(
            self.collection,
            inside_source,
            make_chunks(inside_source, 1),
        )
        sync_document_chunks(
            self.collection,
            outside_source,
            make_chunks(outside_source, 1),
        )

        removed = prune_missing_documents(
            collection=self.collection,
            directory=str(managed_dir),
            current_sources=set(),
        )

        self.assertIn(inside_source, removed)
        self.assertNotIn(outside_source, removed)
        self.assertIsNone(db.get_document_chunks(inside_source))
        self.assertIsNotNone(db.get_document_chunks(outside_source))
        self.assertEqual(self._chroma_chunks(inside_source), [])
        self.assertNotEqual(self._chroma_chunks(outside_source), [])
        self.assertTrue(verify_consistency(self.collection)["is_consistent"])


def run_real_sync():
    setup_logging()

    from src.rag.vector_store import get_collection
    from src.services.indexing_service import (
        build_and_sync,
        print_consistency_report,
    )

    collection = get_collection()

    print("同步前 ChromaDB 数量：", collection.count())

    total = build_and_sync(
        directory="data/documents",
        collection=collection,
        prune_missing=True,
    )

    print("\n本次构建的 Chunk 数量：", total)
    print("同步后 ChromaDB 数量：", collection.count())

    print_consistency_report(verify_consistency(collection))


def run_verify():
    setup_logging()

    from src.rag.vector_store import get_collection
    from src.services.indexing_service import print_consistency_report

    collection = get_collection()
    print_consistency_report(verify_consistency(collection))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="对真实 Markdown 目录执行同步")
    parser.add_argument("--verify", action="store_true", help="检查真实 SQLite 与 ChromaDB 一致性")
    args, _ = parser.parse_known_args()

    if args.real:
        run_real_sync()
    elif args.verify:
        run_verify()
    else:
        unittest.main(verbosity=2)
