from src.config import settings


def _split_turns(messages: list[dict]) -> list[list[dict]]:
    turns = []
    current = []

    for message in messages:
        if message.get("role") == "user" and current:
            turns.append(current)
            current = []
        current.append(message)

    if current:
        turns.append(current)

    return turns


def trim_messages(
    messages: list[dict],
    max_messages: int | None = None,
    keep_system: bool = True,
) -> list[dict]:
    """按轮次裁剪短期消息历史，保留 system 和最近上下文。"""

    max_messages = (
        settings.short_term_memory_max_messages
        if max_messages is None
        else max_messages
    )

    if max_messages <= 0:
        return messages

    if len(messages) <= max_messages:
        return messages

    system_messages = (
        [message for message in messages if message.get("role") == "system"]
        if keep_system
        else []
    )
    non_system_messages = [
        message for message in messages if message.get("role") != "system"
    ]

    budget = max(1, max_messages - len(system_messages))
    turns = _split_turns(non_system_messages)
    selected: list[dict] = []

    for turn in reversed(turns):
        if len(selected) + len(turn) <= budget:
            selected = turn + selected
        else:
            break

    if not selected and turns:
        selected = turns[-1][-budget:]

    return system_messages + selected
