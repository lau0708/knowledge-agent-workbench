
from pathlib import Path
import json
import logging

from src.rag.loader import load_all_markdown, load_markdown
from src.rag.chunker import split_text
from src.rag.embedder import load_embedding_model, encode_texts
from src.rag.vector_store import get_collection, add_chunks

logger = logging.getLogger(__name__)

def build_index(directory: str, chunk_size: int = 200, chunk_overlap: int = 40):
    """读取文档、切分文本，并为每个 Chunk 生成向量。"""

    documents = load_all_markdown(directory)
    chunks = []

    # 第一阶段：读取文档并切分
    for document in documents:
        source = document["source"]
        content = document["content"]

        text_chunks = split_text(
            content,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        for index, text_chunk in enumerate(text_chunks):
            chunks.append({
                "chunk_id": f"{Path(source).stem}_{index}",
                "source": source,
                "chunk_index": index,
                "content": text_chunk,
            })

    # 没有 Chunk 时直接返回，避免不必要的模型加载
    if not chunks:
        return chunks

    # 第二阶段：批量生成向量
    model = load_embedding_model()
    texts = [chunk["content"] for chunk in chunks]
    vectors = encode_texts(model, texts)

    # 第三阶段：将每个向量关联回对应的 Chunk
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = vector.tolist()

    return chunks


def build_document_chunks(
    source: str,
    chunk_size: int = 200,
    chunk_overlap: int = 40,
) -> list[dict]:
    """读取单个 Markdown 文件，切分并生成 Chunk 与 Embedding。"""

    content = load_markdown(source)
    text_chunks = split_text(
        content,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    chunks = [
        {
            "chunk_id": f"{Path(source).stem}_{index}",
            "source": source,
            "chunk_index": index,
            "content": text_chunk,
        }
        for index, text_chunk in enumerate(text_chunks)
    ]

    if not chunks:
        return chunks

    model = load_embedding_model()
    vectors = encode_texts(model, [chunk["content"] for chunk in chunks])

    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = vector.tolist()

    return chunks



def save_index(chunks: list[dict], output_path: str) -> None:
    """将索引保存为 JSON 文件。"""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(chunks, file, ensure_ascii=False)


def build_vector_index(
    directory: str,
    chunk_size: int = 200,
    chunk_overlap: int = 40,
):
    """构建索引并将向量写入 ChromaDB。"""

    # 1. 构建 Chunk 和 Embedding
    chunks = build_index(
        directory,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    if not chunks:
        logger.info("没有找到可索引的文档")
        return 0

    # 2. 获取 ChromaDB Collection
    collection = get_collection()

    # 3. 将向量写入 ChromaDB
    add_chunks(collection, chunks)

    logger.info("向量索引构建完成，共写入 %s 个 Chunk", len(chunks))

    return len(chunks)


if __name__ == "__main__":
    total = build_vector_index("data/documents")

    logger.info("ChromaDB 索引构建完成，共写入 %s 个 Chunk", total)

    collection = get_collection()
    logger.info("ChromaDB 当前数据量：%s", collection.count())
