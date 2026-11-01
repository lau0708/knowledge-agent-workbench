import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

import chromadb

from src.database import db
from src.services import document_service
from src.services.indexing_service import sync_document_chunks


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


class DocumentServiceTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self._old_db_path = db.DB_PATH
        self._old_docs_dir = document_service.DOCUMENTS_DIR

        db.DB_PATH = Path(self.tempdir.name) / "test.db"
        db.init_db()
        document_service.DOCUMENTS_DIR = Path(self.tempdir.name) / "docs"

        self.client = chromadb.EphemeralClient()
        self.collection = self.client.get_or_create_collection(
            name=f"doc_service_{uuid.uuid4().hex}",
            metadata={"hnsw:space": "cosine"},
        )

    def tearDown(self):
        document_service.DOCUMENTS_DIR = self._old_docs_dir
        db.DB_PATH = self._old_db_path
        self.tempdir.cleanup()

    def test_create_list_detail_update_delete(self):
        with patch.object(document_service, "sync_file", side_effect=fake_sync_file):
            created = document_service.create_document(
                self.collection,
                "note.md",
                b"# hello world",
            )

            self.assertEqual(len(document_service.list_documents()), 1)
            self.assertEqual(document_service.get_document(created["id"])["chunks"][0]["content"], "# hello world"[:20])

            updated = document_service.update_document(
                self.collection,
                created["id"],
                "# updated content",
            )
            self.assertEqual(updated["chunks"][0]["content"], "# updated content"[:20])

            deleted = document_service.delete_document(self.collection, created["id"])
            self.assertTrue(deleted["deleted"])
            self.assertEqual(len(document_service.list_documents()), 0)
            self.assertEqual(self.collection.count(), 0)

    def test_duplicate_and_unsupported_upload(self):
        with patch.object(document_service, "sync_file", side_effect=fake_sync_file):
            document_service.create_document(self.collection, "note.md", b"# hello")

            with self.assertRaises(document_service.DuplicateDocumentError):
                document_service.create_document(self.collection, "note.md", b"dup")

            with self.assertRaises(document_service.UnsupportedDocumentTypeError):
                document_service.create_document(self.collection, "note.txt", b"txt")

    def test_update_failure_restores_file(self):
        with patch.object(document_service, "sync_file", side_effect=fake_sync_file):
            created = document_service.create_document(self.collection, "note.md", b"# hello")
            original_content = Path(created["source"]).read_text(encoding="utf-8")

        with patch.object(document_service, "sync_file", side_effect=RuntimeError("boom")):
            with self.assertRaises(document_service.DocumentServiceError):
                document_service.update_document(self.collection, created["id"], "# bad update")

        self.assertEqual(Path(created["source"]).read_text(encoding="utf-8"), original_content)

    def test_delete_failure_restores_file(self):
        with patch.object(document_service, "sync_file", side_effect=fake_sync_file):
            created = document_service.create_document(self.collection, "note.md", b"# hello")
            original_content = Path(created["source"]).read_bytes()

        with patch.object(document_service, "delete_document_sync", side_effect=RuntimeError("boom")):
            with self.assertRaises(document_service.DocumentServiceError):
                document_service.delete_document(self.collection, created["id"])

        self.assertEqual(Path(created["source"]).read_bytes(), original_content)


if __name__ == "__main__":
    unittest.main()
