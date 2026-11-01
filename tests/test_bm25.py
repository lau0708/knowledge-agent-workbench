
from pathlib import Path

from src.rag.bm25_retriever import BM25Retriever, load_chunks
from src.rag.embedder import load_embedding_model
from src.rag.retriever import search
from src.rag.fusion import rrf_fusion
from src.rag.vector_store import get_collection



PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = PROJECT_ROOT / "data" / "index" / "index.json"


def print_results(title, results, score_key):
    print(f"\n{title}")

    for rank, result in enumerate(results, start=1):
        print("-" * 40)
        print("排名：", rank)
        print("来源：", result["source"])
        print("分数：", result[score_key])
        print("内容：", result["content"][:200])


def main():
    chunks = load_chunks(INDEX_PATH)

    # 加载向量模型
    model = load_embedding_model()

    # 初始化 BM25 检索器
    bm25_retriever = BM25Retriever(chunks)

    query = "什么是 Embedding？"

    # 向量检索
    vector_results = search(
        query=query,
        model=model,
        collection=get_collection(),
        top_k=3,
        use_hybrid=False,
    )

    # BM25 检索
    bm25_results = bm25_retriever.search(
        query=query,
        top_k=3,
    )

    print("查询问题：", query)

    print_results(
        "向量检索结果",
        vector_results,
        "score",
    )

    print_results(
        "BM25 检索结果",
        bm25_results,
        "bm25_score",
    )
    # RRF 融合两路检索结果
    hybrid_results = rrf_fusion(
        vector_results=vector_results,
        bm25_results=bm25_results,
        top_k=3,
    )

    print_results(
        "Hybrid Search 检索结果",
        hybrid_results,
        "rrf_score",
    )


if __name__ == "__main__":
    main()
