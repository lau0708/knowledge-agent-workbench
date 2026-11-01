from src.database.db import (
    get_connection,
    init_db,
    insert_document,
)
from src.database.db import delete_document
# 初始化数据库
init_db()


# 清理上一次测试遗留的数据
conn = get_connection()

old_document = conn.execute(
    "SELECT id FROM documents WHERE source = ?",
    ("data/documents/rag-intro.md",),
).fetchone()

conn.close()

if old_document:
    delete_document(old_document["id"])
    print("已清理上一次测试数据")
# 插入文档
conn = get_connection()

document = conn.execute(
    "SELECT id FROM documents WHERE source = ?",
    ("data/documents/rag-intro.md",),
).fetchone()

conn.close()

if document:
    document_id = document["id"]
    print("文档已存在，复用 ID：", document_id)
else:
    document_id = insert_document(
        "data/documents/rag-intro.md"
    )
    print("新文档插入成功，ID：", document_id)

print("插入成功，文档 ID：", document_id)

# 查询文档
conn = get_connection()

document = conn.execute(
    "SELECT * FROM documents WHERE id = ?",
    (document_id,),
).fetchone()

print("查询到的文档：")
print(dict(document))

conn.close()

from src.database.db import insert_chunks

# 测试 Chunk 数据
chunks = [
    {
        "chunk_id": "chunk_001",
        "chunk_index": 0,
        "content": "什么是 RAG？",
    },
    {
        "chunk_id": "chunk_002",
        "chunk_index": 1,
        "content": "Embedding 是将文本转换成向量的技术。",
    },
]

# 插入 Chunk
insert_chunks(
    document_id=document_id,
    chunks=chunks,
)

print("Chunk 插入成功！")

# 查询刚才插入的 Chunk
conn = get_connection()

rows = conn.execute(
    "SELECT * FROM chunks WHERE document_id = ?",
    (document_id,),
).fetchall()

for row in rows:
    print(dict(row))

conn.close()



from src.database.db import delete_document

# 删除文档
deleted = delete_document(document_id)

print("删除文档数量：", deleted)

# 检查关联 Chunk 是否也被删除
conn = get_connection()

rows = conn.execute(
    "SELECT * FROM chunks WHERE document_id = ?",
    (document_id,),
).fetchall()

print("删除后剩余 Chunk 数量：", len(rows))

conn.close()