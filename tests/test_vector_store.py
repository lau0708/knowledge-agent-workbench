
from src.rag.embedder import load_embedding_model, encode_texts
from src.rag.vector_store import get_collection, search_chunks


def main():
    # 1. 加载 Embedding 模型
    model = load_embedding_model()

    # 2. 准备查询问题
    question = "什么是 Embedding？"

    # 3. 将问题转换为向量
    query_vector = encode_texts(model, [question])[0]

    # 4. 获取 ChromaDB 集合
    collection = get_collection()

    collection.delete(
        ids=["test_chunk_0", "test_chunk_1"]
    )

    print("测试数据清理完成")
    print("当前 ChromaDB 数据量：", collection.count())
    # 5. 执行向量检索
    results = search_chunks(
        collection=collection,
        query_embedding=query_vector,
        top_k=2,
    )

    # 6. 打印检索结果
    print("查询问题：", question)
    print("检索结果数量：", len(results))

    for i, chunk in enumerate(results):
        print(f"\n第 {i + 1} 条结果")
        print("Chunk ID：", chunk["chunk_id"])
        print("内容：", chunk["content"])
        print("来源：", chunk["source"])
        print("距离：", chunk["distance"])


if __name__ == "__main__":
    main()
