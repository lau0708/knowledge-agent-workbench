from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MemoryRecord:
    """持久化长期记忆记录。"""

    memory_key: str
    content: str
    owner_id: str = "default"
    source: str = "conversation"
    session_id: str | None = None
    importance: float = 0.5
    expires_at: str | None = None
    id: int | None = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "memory_key": self.memory_key,
            "content": self.content,
            "owner_id": self.owner_id,
            "source": self.source,
            "session_id": self.session_id,
            "importance": self.importance,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row) -> "MemoryRecord":
        return cls(
            id=row["id"],
            memory_key=row["memory_key"],
            content=row["content"],
            owner_id=row["owner_id"],
            source=row["source"],
            session_id=row["session_id"],
            importance=row["importance"],
            expires_at=row["expires_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
