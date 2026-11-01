import threading
import uuid

from src.agent.state import AgentState


class AgentSessionManager:
    """当前进程内的会话状态容器，用于隔离不同 session。"""

    def __init__(self) -> None:
        self._sessions: dict[str, AgentState] = {}
        self._lock = threading.Lock()

    def create(self, user_input: str, session_id: str | None = None) -> AgentState:
        state = AgentState.create(user_input=user_input, session_id=session_id)

        with self._lock:
            self._sessions[state.session_id] = state

        return state

    def get(self, session_id: str) -> AgentState | None:
        with self._lock:
            return self._sessions.get(session_id)

    def save(self, state: AgentState) -> None:
        with self._lock:
            self._sessions[state.session_id] = state

    def remove(self, session_id: str) -> AgentState | None:
        with self._lock:
            return self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        with self._lock:
            return sorted(self._sessions)
