import logging
from datetime import datetime, timezone

from src.database import db
from src.memory.models import MemoryRecord

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_memory_table() -> None:
    """初始化长期记忆表。"""

    conn = db.get_connection()

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                memory_key TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                session_id TEXT,
                importance REAL NOT NULL DEFAULT 0.5,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(owner_id, memory_key)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def save_memory(record: MemoryRecord) -> MemoryRecord:
    """新增或更新长期记忆，冲突时按 owner_id + memory_key 更新。"""

    if not record.memory_key.strip():
        raise ValueError("memory_key 不能为空")
    if not record.content.strip():
        raise ValueError("记忆内容不能为空")

    init_memory_table()
    now = _utc_now()
    conn = db.get_connection()

    try:
        with conn:
            conn.execute(
                """
                INSERT INTO memories (
                    owner_id,
                    memory_key,
                    content,
                    source,
                    session_id,
                    importance,
                    expires_at,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(owner_id, memory_key) DO UPDATE SET
                    content = excluded.content,
                    source = excluded.source,
                    session_id = excluded.session_id,
                    importance = excluded.importance,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    record.owner_id,
                    record.memory_key,
                    record.content,
                    record.source,
                    record.session_id,
                    record.importance,
                    record.expires_at,
                    record.created_at or now,
                    now,
                ),
            )

        row = conn.execute(
            """
            SELECT * FROM memories
            WHERE owner_id = ? AND memory_key = ?
            """,
            (record.owner_id, record.memory_key),
        ).fetchone()

        return MemoryRecord.from_row(row)
    finally:
        conn.close()


def get_memory(memory_id: int) -> MemoryRecord | None:
    init_memory_table()
    conn = db.get_connection()

    try:
        row = conn.execute(
            "SELECT * FROM memories WHERE id = ?",
            (memory_id,),
        ).fetchone()

        return MemoryRecord.from_row(row) if row is not None else None
    finally:
        conn.close()


def list_memories(
    owner_id: str | None = None,
    include_expired: bool = False,
    limit: int = 100,
) -> list[MemoryRecord]:
    init_memory_table()
    conn = db.get_connection()

    try:
        conditions = []
        params: list = []

        if owner_id is not None:
            conditions.append("owner_id = ?")
            params.append(owner_id)

        if not include_expired:
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(_utc_now())

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        rows = conn.execute(
            f"""
            SELECT * FROM memories
            {where}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        return [MemoryRecord.from_row(row) for row in rows]
    finally:
        conn.close()


def search_memories(
    tokens: list[str],
    owner_id: str | None = None,
    include_expired: bool = False,
    limit: int = 5,
) -> list[MemoryRecord]:
    """按关键词检索长期记忆，只返回非过期记录。"""

    if not tokens:
        return []

    init_memory_table()
    conn = db.get_connection()

    try:
        conditions = []
        params: list = []

        if owner_id is not None:
            conditions.append("owner_id = ?")
            params.append(owner_id)

        if not include_expired:
            conditions.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(_utc_now())

        token_conditions = []

        for token in tokens:
            pattern = f"%{token}%"
            token_conditions.append(
                "(content LIKE ? OR memory_key LIKE ? OR source LIKE ?)"
            )
            params.extend([pattern, pattern, pattern])

        if token_conditions:
            conditions.append("(" + " OR ".join(token_conditions) + ")")

        where = "WHERE " + " AND ".join(conditions)
        params.append(limit)

        rows = conn.execute(
            f"""
            SELECT * FROM memories
            {where}
            ORDER BY importance DESC, updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

        return [MemoryRecord.from_row(row) for row in rows]
    finally:
        conn.close()


def update_memory(
    memory_id: int,
    content: str | None = None,
    importance: float | None = None,
    expires_at: str | None = None,
) -> MemoryRecord | None:
    current = get_memory(memory_id)

    if current is None:
        return None

    if content is not None:
        current.content = content
    if importance is not None:
        current.importance = importance
    if expires_at is not None:
        current.expires_at = expires_at

    return save_memory(current)


def delete_memory(memory_id: int) -> bool:
    init_memory_table()
    conn = db.get_connection()

    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE id = ?",
                (memory_id,),
            )
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_memory_by_key(owner_id: str, memory_key: str) -> bool:
    init_memory_table()
    conn = db.get_connection()

    try:
        with conn:
            cursor = conn.execute(
                """
                DELETE FROM memories
                WHERE owner_id = ? AND memory_key = ?
                """,
                (owner_id, memory_key),
            )
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_expired_memories() -> int:
    init_memory_table()
    conn = db.get_connection()

    try:
        with conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (_utc_now(),),
            )
        return cursor.rowcount
    finally:
        conn.close()
