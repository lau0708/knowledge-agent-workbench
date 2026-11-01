from src.rag.bm25_retriever import BM25Retriever
from src.rag.embedder import encode_texts
from src.rag.fusion import rrf_fusion
from src.rag.vector_store import search_chunks

MIN_SIMILARITY = 0.60


def _format_vector_results(results: list[dict]) -> list[dict]:
    """把 ChromaDB distance 转换成统一 score。"""

    return [
        {
            "chunk_id": item["chunk_id"],
            "source": item["source"],
            "content": item["content"],
            "score": 1 - item["distance"],
        }
        for item in results
    ]


def _load_chroma_corpus(collection) -> list[dict]:
    """从 ChromaDB 读取全部 Chunk，作为 BM25 关键词检索语料。"""

    if collection.count() == 0:
        return []

    result = collection.get(include=["documents", "metadatas"])
    ids = result.get("ids", [])
    documents = result.get("documents", [])
    metadatas = result.get("metadatas", [])

    corpus = []

    for index, chunk_id in enumerate(ids):
        metadata = metadatas[index] or {}
        corpus.append(
            {
                "chunk_id": chunk_id,
                "source": metadata.get("source"),
                "chunk_index": metadata.get("chunk_index"),
                "content": documents[index],
            }
        )

    return corpus


def _score_map(vector_results: list[dict], bm25_results: list[dict]) -> dict:
    """把向量相似度和归一化 BM25 分数合并为统一 score。"""

    scores = {}

    for result in vector_results:
        scores[result["chunk_id"]] = max(
            scores.get(result["chunk_id"], 0.0),
            float(result.get("score", 0.0)),
        )

    max_bm25 = max(
        (float(result.get("bm25_score", 0.0)) for result in bm25_results),
        default=0.0,
    )

    for result in bm25_results:
        raw_score = float(result.get("bm25_score", 0.0))
        normalized = raw_score / max_bm25 if max_bm25 else 0.0
        scores[result["chunk_id"]] = max(
            scores.get(result["chunk_id"], 0.0),
            normalized,
        )

    return scores


def search(
    query: str,
    model,
    collection,
    top_k: int = 3,
    use_hybrid: bool = True,
) -> list[dict]:
    """执行向量检索，并默认与 BM25 结果进行 RRF 融合。"""

    if not query.strip():
        raise ValueError("查询问题不能为空")

    if top_k <= 0:
        raise ValueError("top_k 必须大于 0")

    # 1. 将用户问题转换成向量
    query_vector = encode_texts(model, [query])[0]

    vector_results = _format_vector_results(
        search_chunks(
            collection=collection,
            query_embedding=query_vector,
            top_k=top_k,
        )
    )

    if not use_hybrid:
        return vector_results

    bm25_results = BM25Retriever(_load_chroma_corpus(collection)).search(
        query,
        top_k=top_k,
    )

    if not bm25_results:
        return vector_results

    fused_results = rrf_fusion(
        vector_results=vector_results,
        bm25_results=bm25_results,
        top_k=top_k,
    )
    scores = _score_map(vector_results, bm25_results)

    for result in fused_results:
        result["score"] = scores.get(result["chunk_id"], 0.0)

    return fused_results

if __name__ == "__main__":
    from src.rag.embedder import load_embedding_model
    from src.rag.vector_store import get_collection

    model = load_embedding_model()
    collection = get_collection()

    queries = [
        "Embedding 是如何把文字转换成数字向量的？",
        "RAG 是什么，它有什么作用？",
        "Python 是一种什么编程语言？",
    ]

    for query in queries:
        results = search(
            query=query,
            model=model,
            collection=collection,
            top_k=3,
        )

        print("\n" + "=" * 60)
        print(f"查询问题：{query}")

        if not results or results[0]["score"] < MIN_SIMILARITY:
            print("未找到足够相关的知识，暂不回答。")
            continue

        print(f"最高相似度：{results[0]['score']:.4f}")

        for rank, item in enumerate(results, start=1):
            print("-" * 40)
            print(f"排名：{rank}")
            print(f"来源：{item['source']}")
            print(f"相似度：{item['score']:.4f}")
            print(f"内容：{item['content']}")
