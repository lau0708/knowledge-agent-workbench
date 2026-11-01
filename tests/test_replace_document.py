from src.database.db import (
    get_connection,
    init_db,
    replace_document_chunks,
)

SOURCE = "data/documents/replace-test.md"


def main():
    init_db()

    # 清理之前的测试数据
    conn = get_connection()
    conn.execute(
        "DELETE FROM documents WHERE source = ?",
        (SOURCE,),
    )
    conn.commit()
    conn.close()

    # 第一次：写入两个 Chunk
    chunks_v1 = [
        {
            "chunk_id": "replace-test_0",
            "chunk_index": 0,
            "content": "这是第一版文档内容。",
        },
        {
            "chunk_id": "replace-test_1",
            "chunk_index": 1,
            "content": "这是第一版的第二个 Chunk。",
        },
    ]

    document_id = replace_document_chunks(SOURCE, chunks_v1)

    print("第一次写入，文档 ID：", document_id)

    # 第二次：更新为三个 Chunk
    chunks_v2 = [
        {
            "chunk_id": "replace-test_0",
            "chunk_index": 0,
            "content": "这是更新后的文档内容。",
        },
        {
            "chunk_id": "replace-test_1",
            "chunk_index": 1,
            "content": "这是更新后的第二个 Chunk。",
        },
        {
            "chunk_id": "replace-test_2",
            "chunk_index": 2,
            "content": "这是新增的第三个 Chunk。",
        },
    ]

    new_document_id = replace_document_chunks(SOURCE, chunks_v2)

    print("第二次写入，文档 ID：", new_document_id)

    # 查询验证
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT d.source, d.id, c.chunk_id, c.content
        FROM documents d
        JOIN chunks c ON d.id = c.document_id
        WHERE d.source = ?
        ORDER BY c.chunk_index
        """,
        (SOURCE,),
    ).fetchall()

    print("更新后的数据：")

    for row in rows:
        print(dict(row))

    conn.close()


if __name__ == "__main__":
    main()