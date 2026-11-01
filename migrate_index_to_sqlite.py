import json
from pathlib import Path

from src.database.db import get_connection, init_db


PROJECT_ROOT = Path(__file__).resolve().parent
INDEX_PATH = PROJECT_ROOT / "data" / "index" / "index.json"


def migrate():
    # 1. 读取原始 JSON 索引
    with open(INDEX_PATH, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # 2. 按 source 分组
    documents = {}

    for chunk in chunks:
        source = chunk["source"]
        documents.setdefault(source, []).append(chunk)

    conn = get_connection()

    try:
        # 3. 开启事务
        with conn:
            for source, document_chunks in documents.items():

                # 4. 创建文档；如果已存在则复用
                conn.execute(
                    """
                    INSERT INTO documents (source, created_at, updated_at)
                    VALUES (?, datetime('now'), datetime('now'))
                    ON CONFLICT(source) DO UPDATE SET
                        updated_at = datetime('now')
                    """,
                    (source,),
                )

                # 5. 查询文档 ID
                document = conn.execute(
                    "SELECT id FROM documents WHERE source = ?",
                    (source,),
                ).fetchone()

                document_id = document["id"]

                # 6. 写入 Chunk；重复迁移时更新已有记录
                for chunk in document_chunks:
                    conn.execute(
                        """
                        INSERT INTO chunks (
                            chunk_id,
                            document_id,
                            chunk_index,
                            content
                        )
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            document_id = excluded.document_id,
                            chunk_index = excluded.chunk_index,
                            content = excluded.content
                        """,
                        (
                            chunk["chunk_id"],
                            document_id,
                            chunk["chunk_index"],
                            chunk["content"],
                        ),
                    )

        print("迁移完成！")

    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    migrate()