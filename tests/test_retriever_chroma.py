from src.rag.embedder import load_embedding_model
from src.rag.retriever import search
from src.rag.vector_store import get_collection


def main():
    model = load_embedding_model()
    collection = get_collection()

    results = search(
        query="什么是 Embedding？",
        model=model,
        collection=collection,
        top_k=3,
    )

    for i, item in enumerate(results, start=1):
        print(f"\n第 {i} 条结果")
        print("来源：", item["source"])
        print("相似度：", round(item["score"], 4))
        print("内容：", item["content"])


if __name__ == "__main__":
    main()
