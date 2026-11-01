import re
from dataclasses import dataclass


FORGET_PHRASES = [
    "不要记住",
    "别记住",
    "不用记住",
    "忘记这个",
    "忘记我",
    "删除记忆",
    "清除记忆",
]

POSITIVE_SIGNALS = [
    "我喜欢",
    "我偏好",
    "我在学",
    "我正在学",
    "我的项目",
    "我住在",
    "我来自",
    "我使用",
    "我正在做",
    "我计划",
    "我的目标是",
    "记住",
    "以后",
    "我的",
]

TRANSIENT_PREFIXES = [
    "什么是",
    "如何",
    "为什么",
    "怎么",
    "请问",
    "介绍一下",
    "解释",
]

MARKERS = FORGET_PHRASES + ["请记住", "记住"]


@dataclass
class MemoryCandidate:
    """记忆提取结果。"""

    action: str
    memory_key: str
    content: str = ""
    source: str = "conversation"
    importance: float = 0.5


def _normalize(text: str) -> str:
    return text.strip().lower()


def _derive_key(text: str) -> str:
    normalized = _normalize(text)

    for marker in sorted(MARKERS, key=len, reverse=True):
        normalized = normalized.replace(marker, "")

    compact = re.sub(r"\s+", "", normalized)
    return compact[:40] or "memory"


def should_forget(user_input: str) -> bool:
    normalized = _normalize(user_input)
    return any(phrase in normalized for phrase in FORGET_PHRASES)


def should_remember(user_input: str, answer: str) -> bool:
    normalized = _normalize(user_input)

    if should_forget(user_input):
        return False

    if any(signal in normalized for signal in POSITIVE_SIGNALS):
        return True

    if any(normalized.startswith(prefix) for prefix in TRANSIENT_PREFIXES):
        return False

    return False


def extract_memory_candidates(
    user_input: str,
    answer: str,
    owner_id: str = "default",
    session_id: str | None = None,
) -> list[MemoryCandidate]:
    """根据规则决定是否保存或删除长期记忆。"""

    if should_forget(user_input):
        return [
            MemoryCandidate(
                action="forget",
                memory_key=_derive_key(user_input),
                source="conversation",
            )
        ]

    if not should_remember(user_input, answer):
        return []

    content = answer.strip() or user_input.strip()
    importance = 1.0 if "记住" in _normalize(user_input) else 0.8

    return [
        MemoryCandidate(
            action="save",
            memory_key=_derive_key(user_input),
            content=content,
            source="conversation",
            importance=importance,
        )
    ]
