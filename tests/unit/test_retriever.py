import unittest
import uuid
from unittest.mock import patch

import chromadb

from src.rag.retriever import search


class FakeQueryVector:
    def tolist(self):
        return [1.0, 0.0, 0.0]


class HybridRetrieverTest(unittest.TestCase):
    def setUp(self):
        self.client = chromadb.EphemeralClient()
        self.collection = self.client.get_or_create_collection(
            name=f"hybrid_retriever_{uuid.uuid4().hex}",
            metadata={"hnsw:space": "cosine"},
        )
        self.collection.upsert(
            ids=["chunk_a", "chunk_b"],
            documents=["alpha beta gamma", "delta epsilon"],
            embeddings=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            metadatas=[
                {"source": "a.md", "chunk_index": 0},
                {"source": "b.md", "chunk_index": 0},
            ],
        )

    def test_vector_only_search_returns_vector_candidate(self):
        with patch(
            "src.rag.retriever.encode_texts",
            return_value=[FakeQueryVector()],
        ):
            results = search(
                query="alpha",
                model=object(),
                collection=self.collection,
                top_k=2,
                use_hybrid=False,
            )

        self.assertEqual(results[0]["chunk_id"], "chunk_a")
        self.assertIn("score", results[0])

    def test_hybrid_search_combines_vector_and_bm25(self):
        with patch(
            "src.rag.retriever.encode_texts",
            return_value=[FakeQueryVector()],
        ):
            results = search(
                query="alpha",
                model=object(),
                collection=self.collection,
                top_k=2,
            )

        self.assertTrue(results)
        self.assertEqual(results[0]["chunk_id"], "chunk_a")
        self.assertEqual(results[0]["source"], "a.md")
        self.assertIn("rrf_score", results[0])
        self.assertIn("score", results[0])
        self.assertGreaterEqual(results[0]["score"], 0.0)


if __name__ == "__main__":
    unittest.main()
