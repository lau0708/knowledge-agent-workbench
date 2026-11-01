from src.database.db import get_connection
from src.rag.vector_store import get_collection


def main():
    # 1. 检查 SQLite
    conn = get_connection()

    documents = conn.execute(
        "SELECT id, source FROM documents ORDER BY id"
    ).fetchall()

    chunk_count = conn.execute(
        "SELECT COUNT(*) AS total FROM chunks"
    ).fetchone()["total"]

    print("===== SQLite =====")
    print("文档数量：", len(documents))
    print("Chunk 数量：", chunk_count)

    for document in documents:
        print(dict(document))

    conn.close()

    # 2. 检查 ChromaDB
    collection = get_collection()

    print("\n===== ChromaDB =====")
    print("Chunk 数量：", collection.count())

    result = collection.get(include=["metadatas"])

    sources = sorted({
        metadata["source"]
        for metadata in result["metadatas"]
        if metadata and "source" in metadata
    })

    print("文档来源：")
    for source in sources:
        print(source)


if __name__ == "__main__":
    main()