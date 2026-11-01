
import chromadb

from src.config import settings

CHROMA_PATH = settings.chroma_path
COLLECTION_NAME = settings.chroma_collection_name

def get_collection():
    """获取或创建本地持久化向量集合。"""

    # 1. 创建本地持久化客户端
    client = chromadb.PersistentClient(
        path=str(CHROMA_PATH)
    )

    # 2. 获取或创建 Collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "hnsw:space": "cosine"
        }
    )

    return collection

def add_chunks(collection, chunks: list[dict]):
    """将 Chunk 及其向量写入 ChromaDB。"""

    if not chunks:
        return

    collection.upsert(
        ids=[
            chunk["chunk_id"]
            for chunk in chunks
        ],
        documents=[
            chunk["content"]
            for chunk in chunks
        ],
        embeddings=[
            chunk["embedding"].tolist()
            if hasattr(chunk["embedding"], "tolist")
            else chunk["embedding"]
            for chunk in chunks
        ],
        metadatas=[
            {
                "source": chunk["source"],
                "chunk_index": chunk["chunk_index"],
            }
            for chunk in chunks
        ],
    )


def get_chunks_by_source(collection, source: str) -> list[dict]:
    """读取 ChromaDB 中某个 source 的全部 Chunk 快照。"""

    result = collection.get(
        where={"source": source},
        include=["embeddings", "documents", "metadatas"],
    )

    return [
        {
            "id": result["ids"][index],
            "embedding": result["embeddings"][index],
            "document": result["documents"][index],
            "metadata": result["metadatas"][index],
        }
        for index in range(len(result["ids"]))
    ]


def delete_chunks_by_source(collection, source: str) -> None:
    """删除 ChromaDB 中某个 source 的全部 Chunk。"""

    collection.delete(where={"source": source})


def restore_chunks(collection, records: list[dict]) -> None:
    """用同步前的 ChromaDB 快照恢复 Chunk，用于失败补偿。"""

    if not records:
        return

    collection.upsert(
        ids=[record["id"] for record in records],
        documents=[record["document"] for record in records],
        embeddings=[record["embedding"] for record in records],
        metadatas=[record["metadata"] for record in records],
    )


def get_all_sources(collection) -> set[str]:
    """读取 ChromaDB 中全部文档来源。"""

    result = collection.get(include=["metadatas"])

    return {
        metadata["source"]
        for metadata in result["metadatas"]
        if metadata and "source" in metadata
    }


def search_chunks(collection, query_embedding, top_k: int = 3):
    """根据查询向量检索最相关的 Chunk。"""

    if collection.count() == 0:
        return []

    result = collection.query(
        query_embeddings=[
            query_embedding.tolist()
        ],
        n_results=min(top_k, collection.count()),
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    chunks = []

    for i in range(len(result["ids"][0])):
        chunks.append({
            "chunk_id": result["ids"][0][i],
            "content": result["documents"][0][i],
            "source": result["metadatas"][0][i]["source"],
            "chunk_index": result["metadatas"][0][i]["chunk_index"],
            "distance": result["distances"][0][i],
        })

    return chunks
