from src.memory.memory_store import search_memories
from src.rag.bm25_retriever import tokenize


def retrieve_relevant_memories(
    query: str,
    owner_id: str = "default",
    limit: int = 5,
) -> list[dict]:
    """根据当前输入检索相关长期记忆。"""

    tokens = [token for token in tokenize(query) if token]

    if not tokens:
        return []

    records = search_memories(
        tokens=tokens,
        owner_id=owner_id,
        limit=limit,
    )

    return [record.to_dict() for record in records]


def format_memories(memories: list[dict]) -> str:
    """把检索到的记忆整理成可注入上下文的文本。"""

    if not memories:
        return ""

    lines = ["[长期记忆]"]

    for memory in memories:
        lines.append(f"- {memory['content']}")

    return "\n".join(lines)
