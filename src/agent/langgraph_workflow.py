import logging
from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from src.agent.state import AgentState
from src.agent.workflow import (
    WorkflowError,
    _default_analyze_intent,
    _default_generate_summary,
    _default_is_sufficient,
    _default_supplement_query,
)
from src.config import settings
from src.rag.retriever import search as vector_search

logger = logging.getLogger(__name__)


class KnowledgeGraphState(TypedDict, total=False):
    """LangGraph 图状态，agent_state 复用现有 AgentState。"""

    session_id: str
    user_input: str
    agent_state: AgentState
    query: str
    needs_retrieval: bool
    retrieval_attempts: int
    retrieval_results: list[dict]
    retrieval_error: str | None
    is_sufficient_result: bool
    supplement_count: int
    summary: str | None
    max_supplement_attempts: int
    max_summary_retries: int
    top_k: int


@dataclass
class LangGraphDependencies:
    """图节点需要的模型、集合和可注入业务函数。"""

    model: Any
    collection: Any
    top_k: int = settings.top_k
    max_supplement_attempts: int = settings.workflow_max_supplement_attempts
    max_summary_retries: int = settings.workflow_max_summary_retries
    analyze_intent: Callable[[str], dict] = _default_analyze_intent
    is_sufficient: Callable[[list[dict]], bool] = _default_is_sufficient
    generate_summary: Callable[..., str] = _default_generate_summary
    supplement_query: Callable[..., str] = _default_supplement_query
    search: Callable[..., list[dict]] | None = None

    def get_search(self) -> Callable[..., list[dict]]:
        if self.search is not None:
            return self.search

        return lambda query, top_k: vector_search(
            query=query,
            model=self.model,
            collection=self.collection,
            top_k=top_k,
        )


def _dependencies(config: dict) -> LangGraphDependencies:
    return config["configurable"]["workflow_dependencies"]


def analyze_node(state: KnowledgeGraphState, config: dict) -> dict:
    agent_state = state["agent_state"]
    deps = _dependencies(config)
    question = state.get("user_input") or agent_state.user_input
    agent_state.add_workflow_event("analyze", "start")

    try:
        intent = deps.analyze_intent(question)
        query = intent.get("query") or question
        needs_retrieval = bool(intent.get("needs_retrieval", True))
        agent_state.add_workflow_event("analyze", "completed")
        return {
            "agent_state": agent_state,
            "query": query,
            "needs_retrieval": needs_retrieval,
        }
    except Exception as exc:
        agent_state.add_workflow_event("analyze", "failed", str(exc))
        raise


def retrieve_node(state: KnowledgeGraphState, config: dict) -> dict:
    agent_state = state["agent_state"]
    deps = _dependencies(config)
    query = state.get("query") or agent_state.user_input
    top_k = state.get("top_k", deps.top_k)
    attempts = state.get("retrieval_attempts", 0) + 1
    agent_state.add_workflow_event("retrieve", "start")

    try:
        results = deps.get_search()(query=query, top_k=top_k)
    except Exception as exc:
        logger.exception("LangGraph 检索失败 query=%s", query)
        agent_state.add_workflow_event("retrieve", "completed")
        return {
            "agent_state": agent_state,
            "retrieval_attempts": attempts,
            "retrieval_results": [],
            "retrieval_error": str(exc),
        }

    agent_state.add_workflow_event("retrieve", "completed")
    return {
        "agent_state": agent_state,
        "retrieval_attempts": attempts,
        "retrieval_results": results,
        "retrieval_error": None,
    }


def check_sufficiency_node(state: KnowledgeGraphState, config: dict) -> dict:
    agent_state = state["agent_state"]
    deps = _dependencies(config)
    results = state.get("retrieval_results", [])
    agent_state.add_workflow_event("check_sufficiency", "start")

    try:
        sufficient = deps.is_sufficient(results)
    except Exception as exc:
        agent_state.add_workflow_event("check_sufficiency", "failed", str(exc))
        raise

    agent_state.add_workflow_event("check_sufficiency", "completed")
    return {
        "agent_state": agent_state,
        "is_sufficient_result": sufficient,
    }


def supplement_node(state: KnowledgeGraphState, config: dict) -> dict:
    agent_state = state["agent_state"]
    deps = _dependencies(config)
    question = state.get("user_input") or agent_state.user_input
    current_query = state.get("query") or question
    attempt = state.get("retrieval_attempts", 0) + 1
    agent_state.add_workflow_event("supplement", "start")

    try:
        new_query = deps.supplement_query(
            question=question,
            current_query=current_query,
            attempt=attempt,
        )
    except Exception as exc:
        agent_state.add_workflow_event("supplement", "failed", str(exc))
        raise

    agent_state.add_workflow_event("supplement", "completed")
    return {
        "agent_state": agent_state,
        "query": new_query,
        "supplement_count": state.get("supplement_count", 0) + 1,
    }


def summarize_node(state: KnowledgeGraphState, config: dict) -> dict:
    agent_state = state["agent_state"]
    deps = _dependencies(config)
    question = state.get("user_input") or agent_state.user_input
    results = state.get("retrieval_results", [])
    max_retries = state.get("max_summary_retries", deps.max_summary_retries)
    agent_state.add_workflow_event("summarize", "start")

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            answer = deps.generate_summary(question=question, results=results)
            agent_state.add_message("assistant", answer)
            agent_state.mark_completed(answer)
            agent_state.add_workflow_event("summarize", "completed")
            return {
                "agent_state": agent_state,
                "summary": answer,
            }
        except Exception as exc:
            last_error = exc
            logger.warning(
                "LangGraph 总结生成失败 attempt=%s error=%s",
                attempt + 1,
                exc,
            )

    agent_state.add_workflow_event("summarize", "failed", str(last_error))
    raise WorkflowError(f"总结生成失败：{last_error}")


def insufficient_node(state: KnowledgeGraphState, config: dict) -> dict:
    agent_state = state["agent_state"]
    agent_state.add_workflow_event("insufficient", "start")

    retrieval_error = state.get("retrieval_error")
    message = "知识库检索结果不足，无法生成可靠总结。"
    if retrieval_error:
        message += f"检索失败原因：{retrieval_error}"

    agent_state.mark_failed(message)
    agent_state.add_workflow_event("insufficient", "completed")
    return {
        "agent_state": agent_state,
        "summary": None,
    }


def route_after_analyze(state: KnowledgeGraphState) -> str:
    if state.get("needs_retrieval", True):
        return "retrieve"
    return "summarize"


def route_after_check(state: KnowledgeGraphState) -> str:
    if state.get("is_sufficient_result"):
        return "summarize"

    attempts = state.get("retrieval_attempts", 0)
    max_supplement = state.get(
        "max_supplement_attempts",
        settings.workflow_max_supplement_attempts,
    )

    if attempts < max_supplement:
        return "supplement"

    return "insufficient"


def build_knowledge_graph():
    """构建并编译 LangGraph 知识库任务图。"""

    builder = StateGraph(KnowledgeGraphState)
    builder.add_node("analyze", analyze_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("check_sufficiency", check_sufficiency_node)
    builder.add_node("supplement", supplement_node)
    builder.add_node("summarize", summarize_node)
    builder.add_node("insufficient", insufficient_node)

    builder.add_edge(START, "analyze")
    builder.add_conditional_edges(
        "analyze",
        route_after_analyze,
        {
            "retrieve": "retrieve",
            "summarize": "summarize",
        },
    )
    builder.add_edge("retrieve", "check_sufficiency")
    builder.add_conditional_edges(
        "check_sufficiency",
        route_after_check,
        {
            "summarize": "summarize",
            "supplement": "supplement",
            "insufficient": "insufficient",
        },
    )
    builder.add_edge("supplement", "retrieve")
    builder.add_edge("summarize", END)
    builder.add_edge("insufficient", END)

    return builder.compile()


def build_langgraph_dependencies(
    model,
    collection,
    overrides: dict | None = None,
) -> LangGraphDependencies:
    values: dict[str, Any] = {}

    if overrides:
        values.update(overrides)

    return LangGraphDependencies(
        model=model,
        collection=collection,
        top_k=values.get("top_k", settings.top_k),
        max_supplement_attempts=values.get(
            "max_supplement_attempts",
            settings.workflow_max_supplement_attempts,
        ),
        max_summary_retries=values.get(
            "max_summary_retries",
            settings.workflow_max_summary_retries,
        ),
        analyze_intent=values.get("analyze_intent", _default_analyze_intent),
        is_sufficient=values.get("is_sufficient", _default_is_sufficient),
        generate_summary=values.get("generate_summary", _default_generate_summary),
        supplement_query=values.get("supplement_query", _default_supplement_query),
        search=values.get("search"),
    )


def run_langgraph_workflow(
    question: str,
    model,
    collection,
    state: AgentState | None = None,
    session_id: str | None = None,
    context_overrides: dict | None = None,
) -> AgentState:
    """运行 LangGraph 版知识库检索与总结流程。"""

    if state is None:
        state = AgentState.create(user_input=question, session_id=session_id)
    else:
        state.user_input = question

    state.add_message("user", question)
    state.start()

    deps = build_langgraph_dependencies(model, collection, context_overrides)
    graph = build_knowledge_graph()

    initial_state: KnowledgeGraphState = {
        "session_id": state.session_id,
        "user_input": question,
        "agent_state": state,
        "query": question,
        "needs_retrieval": True,
        "retrieval_attempts": 0,
        "retrieval_results": [],
        "retrieval_error": None,
        "is_sufficient_result": False,
        "supplement_count": 0,
        "summary": None,
        "max_supplement_attempts": deps.max_supplement_attempts,
        "max_summary_retries": deps.max_summary_retries,
        "top_k": deps.top_k,
    }

    config = {"configurable": {"workflow_dependencies": deps}}

    try:
        final_state = graph.invoke(initial_state, config)
        return final_state["agent_state"]
    except Exception as exc:
        logger.exception("LangGraph Workflow 执行失败")
        state.mark_failed(f"LangGraph Workflow 节点失败：{exc}")
        return state
