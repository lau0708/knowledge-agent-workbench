from src.config import settings
from src.memory import memory_store
from src.memory.memory_extractor import (
    MemoryCandidate,
    extract_memory_candidates,
)
from src.memory.memory_retriever import (
    format_memories,
    retrieve_relevant_memories,
)
from src.memory.models import MemoryRecord
from src.memory.short_term import trim_messages


class MemoryService:
    """短期历史裁剪与长期记忆读写服务。"""

    def __init__(
        self,
        store=None,
        extractor=extract_memory_candidates,
        short_term_max_messages: int | None = None,
    ) -> None:
        self.store = store if store is not None else memory_store
        self.extractor = extractor
        self.short_term_max_messages = (
            settings.short_term_memory_max_messages
            if short_term_max_messages is None
            else short_term_max_messages
        )

    def init(self) -> None:
        self.store.init_memory_table()

    def retrieve_relevant(
        self,
        query: str,
        owner_id: str = "default",
        limit: int = 5,
    ) -> list[dict]:
        return retrieve_relevant_memories(
            query=query,
            owner_id=owner_id,
            limit=limit,
        )

    def build_context_block(
        self,
        query: str,
        owner_id: str = "default",
        limit: int = 3,
    ) -> str:
        memories = self.retrieve_relevant(query, owner_id=owner_id, limit=limit)
        return format_memories(memories)

    def remember_turn(
        self,
        user_input: str,
        answer: str,
        owner_id: str = "default",
        session_id: str | None = None,
    ) -> list[MemoryCandidate]:
        candidates = self.extractor(
            user_input,
            answer,
            owner_id=owner_id,
            session_id=session_id,
        )

        for candidate in candidates:
            if candidate.action == "save":
                self.store.save_memory(
                    MemoryRecord(
                        memory_key=candidate.memory_key,
                        content=candidate.content,
                        owner_id=owner_id,
                        source=candidate.source,
                        session_id=session_id,
                        importance=candidate.importance,
                    )
                )
            elif candidate.action == "forget":
                self.store.delete_memory_by_key(owner_id, candidate.memory_key)

        return candidates

    def save_memory(self, record: MemoryRecord) -> MemoryRecord:
        return self.store.save_memory(record)

    def delete_memory(self, memory_id: int) -> bool:
        return self.store.delete_memory(memory_id)

    def trim_short_term(
        self,
        messages: list[dict],
        max_messages: int | None = None,
    ) -> list[dict]:
        return trim_messages(
            messages,
            max_messages=max_messages or self.short_term_max_messages,
        )


def init_memory_table() -> None:
    memory_store.init_memory_table()
