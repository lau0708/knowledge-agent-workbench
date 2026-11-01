import sqlite3
from datetime import datetime

from src.config import settings

# 数据库文件路径
DB_PATH = settings.database_path


def get_connection():
    """创建 SQLite 数据库连接。"""

    # 确保数据库目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # 创建数据库连接
    conn = sqlite3.connect(DB_PATH)

    # 将查询结果转换为类似字典的结构
    conn.row_factory = sqlite3.Row

    # 启用外键约束
    conn.execute("PRAGMA foreign_keys = ON")

    return conn

def init_db():
    """初始化数据库表。"""

    conn = get_connection()

    # 创建 documents 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # 创建 chunks 表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id TEXT PRIMARY KEY,
            document_id INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,

            FOREIGN KEY (document_id)
                REFERENCES documents(id)
                ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()

def insert_document(source: str) -> int:
    """插入文档记录，返回文档 ID。"""

    conn = get_connection()

    now = datetime.now().isoformat(timespec="seconds")

    cursor = conn.execute(
        """
        INSERT INTO documents (source, created_at, updated_at)
        VALUES (?, ?, ?)
        """,
        (source, now, now),
    )

    # 获取刚刚插入记录的自增 ID
    document_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return document_id

def insert_chunks(document_id: int, chunks: list[dict]):
    """批量插入 Chunk 数据。"""

    conn = get_connection()

    values = [
        (
            chunk["chunk_id"],
            document_id,
            chunk["chunk_index"],
            chunk["content"],
        )
        for chunk in chunks
    ]

    conn.executemany(
        """
        INSERT INTO chunks (
            chunk_id,
            document_id,
            chunk_index,
            content
        )
        VALUES (?, ?, ?, ?)
        """,
        values,
    )

    conn.commit()
    conn.close()


def delete_document(document_id: int):
    """删除文档及其关联的所有 Chunk。"""

    conn = get_connection()

    cursor = conn.execute(
        "DELETE FROM documents WHERE id = ?",
        (document_id,),
    )

    deleted = cursor.rowcount

    conn.commit()
    conn.close()

    return deleted


def replace_document_chunks(source: str, chunks: list[dict]) -> int:
    """新增或更新文档，并替换该文档的全部 Chunk。"""

    if not source.strip():
        raise ValueError("文档来源不能为空")

    conn = get_connection()

    try:
        # 使用事务保证文档和 Chunk 的修改一起成功或一起回滚
        with conn:
            now = datetime.now().isoformat(timespec="seconds")

            # 1. 创建文档；如果已存在，则更新时间
            conn.execute(
                """
                INSERT INTO documents (source, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    updated_at = excluded.updated_at
                """,
                (source, now, now),
            )

            # 2. 查询文档 ID
            document = conn.execute(
                "SELECT id FROM documents WHERE source = ?",
                (source,),
            ).fetchone()

            document_id = document["id"]

            # 3. 删除该文档原有的 Chunk
            conn.execute(
                "DELETE FROM chunks WHERE document_id = ?",
                (document_id,),
            )

            # 4. 插入本次最新的 Chunk
            values = [
                (
                    chunk["chunk_id"],
                    document_id,
                    chunk["chunk_index"],
                    chunk["content"],
                )
                for chunk in chunks
            ]

            if values:
                conn.executemany(
                    """
                    INSERT INTO chunks (
                        chunk_id,
                        document_id,
                        chunk_index,
                        content
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    values,
                )

        return document_id

    finally:
        conn.close()


def get_document_chunks(source: str) -> dict | None:
    """读取单个文档及其 Chunk，作为同步前的 SQLite 快照。"""

    conn = get_connection()

    try:
        document = conn.execute(
            "SELECT id, source, created_at, updated_at FROM documents WHERE source = ?",
            (source,),
        ).fetchone()

        if document is None:
            return None

        rows = conn.execute(
            """
            SELECT chunk_id, chunk_index, content
            FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_index
            """,
            (document["id"],),
        ).fetchall()

        return {
            "source": source,
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
            "chunks": [
                {
                    "chunk_id": row["chunk_id"],
                    "chunk_index": row["chunk_index"],
                    "content": row["content"],
                }
                for row in rows
            ],
        }

    finally:
        conn.close()


def restore_document_snapshot(source: str, snapshot: dict | None) -> None:
    """用同步前的 SQLite 快照恢复文档和 Chunk，用于失败补偿。"""

    conn = get_connection()

    try:
        with conn:
            if snapshot is None:
                conn.execute(
                    "DELETE FROM documents WHERE source = ?",
                    (source,),
                )
                return

            conn.execute(
                """
                INSERT INTO documents (source, created_at, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    snapshot["source"],
                    snapshot["created_at"],
                    snapshot["updated_at"],
                ),
            )

            document = conn.execute(
                "SELECT id FROM documents WHERE source = ?",
                (source,),
            ).fetchone()

            conn.execute(
                "DELETE FROM chunks WHERE document_id = ?",
                (document["id"],),
            )

            values = [
                (
                    chunk["chunk_id"],
                    document["id"],
                    chunk["chunk_index"],
                    chunk["content"],
                )
                for chunk in snapshot["chunks"]
            ]

            if values:
                conn.executemany(
                    """
                    INSERT INTO chunks (
                        chunk_id,
                        document_id,
                        chunk_index,
                        content
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    values,
                )

    finally:
        conn.close()


def delete_document_by_source(source: str) -> int:
    """按 source 删除文档，Chunk 通过外键级联删除。"""

    conn = get_connection()

    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM documents WHERE source = ?",
                (source,),
            )
            return cursor.rowcount

    finally:
        conn.close()


def get_all_document_sources() -> set[str]:
    """读取 SQLite 中所有文档来源。"""

    conn = get_connection()

    try:
        rows = conn.execute("SELECT source FROM documents").fetchall()
        return {row["source"] for row in rows}

    finally:
        conn.close()


def get_all_chunks_by_source() -> dict[str, dict[str, str]]:
    """读取 SQLite 中每个文档的 Chunk ID 与内容，用于一致性检查。"""

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT d.source, c.chunk_id, c.content
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            """
        ).fetchall()

        chunks_by_source = {}

        for row in rows:
            chunks_by_source.setdefault(row["source"], {})[row["chunk_id"]] = row["content"]

        return chunks_by_source

    finally:
        conn.close()


def get_document_id_by_source(source: str) -> int | None:
    """根据文档来源查询文档 ID。"""

    conn = get_connection()

    try:
        row = conn.execute(
            "SELECT id FROM documents WHERE source = ?",
            (source,),
        ).fetchone()

        return row["id"] if row is not None else None

    finally:
        conn.close()


def get_document_by_id(document_id: int) -> dict | None:
    """读取文档详情及其全部 Chunk。"""

    conn = get_connection()

    try:
        document = conn.execute(
            """
            SELECT id, source, created_at, updated_at
            FROM documents
            WHERE id = ?
            """,
            (document_id,),
        ).fetchone()

        if document is None:
            return None

        rows = conn.execute(
            """
            SELECT chunk_id, chunk_index, content
            FROM chunks
            WHERE document_id = ?
            ORDER BY chunk_index
            """,
            (document_id,),
        ).fetchall()

        return {
            "id": document["id"],
            "source": document["source"],
            "created_at": document["created_at"],
            "updated_at": document["updated_at"],
            "chunks": [
                {
                    "chunk_id": row["chunk_id"],
                    "chunk_index": row["chunk_index"],
                    "content": row["content"],
                }
                for row in rows
            ],
        }

    finally:
        conn.close()


def get_all_documents() -> list[dict]:
    """读取文档列表，并统计每个文档的 Chunk 数量。"""

    conn = get_connection()

    try:
        rows = conn.execute(
            """
            SELECT
                d.id,
                d.source,
                d.created_at,
                d.updated_at,
                COUNT(c.chunk_id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.id
            """
        ).fetchall()

        return [
            {
                "id": row["id"],
                "source": row["source"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "chunk_count": row["chunk_count"],
            }
            for row in rows
        ]

    finally:
        conn.close()
