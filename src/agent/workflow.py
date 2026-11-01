import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from src.agent.state import AgentState
from src.config import settings
from src.rag.llm import call_deepseek
from src.rag.retriever import search as vector_search

logger = logging.getLogger(__name__)


class WorkflowError(Exception):
    """Workflow 执行或路由失败。"""


@dataclass
class NodeResult:
    """节点执行结果，可显式指定下一个节点。"""

    output: Any = None
    next_node: str | None = None


@dataclass
class WorkflowNode:
    """Workflow 节点，handler 返回 NodeResult。"""

    name: str
    handler: Callable[[AgentState, dict], NodeResult]
    next_node: str | None = None


class Workflow:
    """轻量 Workflow 执行器：顺序执行、条件路由和有限循环。"""

    def __init__(
        self,
        nodes: list[WorkflowNode],
        start_node: str,
        max_steps: int | None = None,
    ) -> None:
        self.nodes = {node.name: node for node in nodes}
        self.start_node = start_node
        self.max_steps = (
            settings.workflow_max_steps if max_steps is None else max_steps
        )

    def run(self, state: AgentState, context: dict) -> AgentState:
        if self.start_node not in self.nodes:
            raise WorkflowError(f"起始节点不存在：{self.start_node}")

        state.start()
        current_node = self.start_node
        steps = 0

        while current_node is not None:
            if steps >= self.max_steps:
                state.mark_failed(f"Workflow 超过最大步数：{self.max_steps}")
                return state

            node = self.nodes[current_node]
            state.add_workflow_event(current_node, "start")

            try:
                result = node.handler(state, context)
            except Exception as exc:
                logger.exception("Workflow 节点执行失败 node=%s", current_node)
                state.add_workflow_event(current_node, "failed", str(exc))
                state.mark_failed(f"Workflow 节点失败：{current_node}：{exc}")
                return state

            state.add_workflow_event(current_node, "completed")

            next_node = result.next_node if result.next_node is not None else node.next_node

            if next_node is not None and next_node not in self.nodes:
                state.add_workflow_event(
                    current_node,
                    "failed",
                    f"未知节点：{next_node}",
                )
                state.mark_failed(f"Workflow 路由到未知节点：{next_node}")
                return state

            current_node = next_node
            steps += 1

        return state


def _default_analyze_intent(question: str) -> dict:
    prompt = (
        "判断用户问题是否需要检索本地知识库。"
        '只输出 JSON：{"needs_retrieval": true 或 false, "query": "检索词"}。'
        f"\n用户问题：{question}"
    )

    try:
        content = call_deepseek(prompt)
        data = json.loads(content)
        return {
            "needs_retrieval": bool(data.get("needs_retrieval", True)),
            "query": str(data.get("query") or question),
        }
    except Exception as exc:
        logger.warning("意图分析失败，默认进入检索流程：%s", exc)
        return {"needs_retrieval": True, "query": question}


def _default_is_sufficient(results: list[dict]) -> bool:
    if not results:
        return False

    return any(
        float(item.get("score", 0.0)) >= settings.min_similarity
        for item in results
    )


def _build_summary_prompt(question: str, results: list[dict]) -> str:
    context_parts = [
        f"参考资料{i}：\n{item.get('content', '')}"
        for i, item in enumerate(results, start=1)
    ]
    context = "\n\n".join(context_parts)

    return (
        "你是本地知识库助手，请根据参考资料整理一份总结。"
        "如果资料不足，请明确说明。\n\n"
        f"参考资料：\n{context}\n\n"
        f"用户问题：{question}\n"
        "总结："
    )


def _default_generate_summary(question: str, results: list[dict]) -> str:
    if not results:
        return "知识库中没有找到足够相关资料，无法生成总结。"

    prompt = _build_summary_prompt(question, results)
    return call_deepseek(prompt)


def _default_supplement_query(
    question: str,
    current_query: str,
    attempt: int,
) -> str:
    return f"{question} 补充检索（第{attempt}次）：{current_query}"


def analyze_node(state: AgentState, context: dict) -> NodeResult:
    question = state.user_input
    analyze_intent = context.get("analyze_intent", _default_analyze_intent)
    intent = analyze_intent(question)

    context["intent"] = intent
    context["query"] = intent.get("query") or question
    context["needs_retrieval"] = bool(intent.get("needs_retrieval", True))

    if context["needs_retrieval"]:
        return NodeResult(output=intent, next_node="retrieve")

    return NodeResult(output=intent, next_node="summarize")


def retrieve_node(state: AgentState, context: dict) -> NodeResult:
    query = context.get("query") or state.user_input
    top_k = context.get("top_k", settings.top_k)
    search_fn = context.get("search")

    context["retrieval_attempts"] = context.get("retrieval_attempts", 0) + 1

    try:
        results = search_fn(query=query, top_k=top_k)
    except Exception as exc:
        logger.exception("知识库检索失败 query=%s", query)
        context["retrieval_error"] = str(exc)
        context["retrieval_results"] = []
        return NodeResult(output=[], next_node="check_sufficiency")

    context["retrieval_error"] = None
    context["retrieval_results"] = results
    return NodeResult(output=results, next_node="check_sufficiency")


def check_sufficiency_node(state: AgentState, context: dict) -> NodeResult:
    results = context.get("retrieval_results", [])
    is_sufficient = context.get("is_sufficient", _default_is_sufficient)
    sufficient = is_sufficient(results)
    context["is_sufficient_result"] = sufficient

    if sufficient:
        return NodeResult(output=True, next_node="summarize")

    attempts = context.get("retrieval_attempts", 0)
    max_supplement = context.get(
        "max_supplement_attempts",
        settings.workflow_max_supplement_attempts,
    )

    if attempts < max_supplement:
        return NodeResult(output=False, next_node="supplement")

    return NodeResult(output=False, next_node="insufficient")


def supplement_node(state: AgentState, context: dict) -> NodeResult:
    question = state.user_input
    current_query = context.get("query") or question
    supplement_query = context.get("supplement_query", _default_supplement_query)
    attempt = context.get("retrieval_attempts", 0) + 1

    new_query = supplement_query(
        question=question,
        current_query=current_query,
        attempt=attempt,
    )

    context["query"] = new_query
    context["supplement_count"] = context.get("supplement_count", 0) + 1

    return NodeResult(output=new_query, next_node="retrieve")


def summarize_node(state: AgentState, context: dict) -> NodeResult:
    question = state.user_input
    results = context.get("retrieval_results", [])
    generate_summary = context.get("generate_summary", _default_generate_summary)
    max_retries = context.get(
        "max_summary_retries",
        settings.workflow_max_summary_retries,
    )

    last_error = None

    for attempt in range(max_retries + 1):
        try:
            answer = generate_summary(question=question, results=results)
            context["summary"] = answer
            state.add_message("assistant", answer)
            state.mark_completed(answer)
            return NodeResult(output=answer)
        except Exception as exc:
            last_error = exc
            logger.warning(
                "总结生成失败 attempt=%s error=%s",
                attempt + 1,
                exc,
            )

    raise WorkflowError(f"总结生成失败：{last_error}")


def insufficient_node(state: AgentState, context: dict) -> NodeResult:
    retrieval_error = context.get("retrieval_error")
    default_message = "知识库检索结果不足，无法生成可靠总结。"
    if retrieval_error:
        default_message += f"检索失败原因：{retrieval_error}"

    message = context.get("insufficient_message", default_message)
    context["insufficient_message"] = message
    state.mark_failed(message)
    return NodeResult(output=message)


def build_knowledge_workflow(max_steps: int | None = None) -> Workflow:
    return Workflow(
        nodes=[
            WorkflowNode("analyze", analyze_node, next_node="retrieve"),
            WorkflowNode("retrieve", retrieve_node, next_node="check_sufficiency"),
            WorkflowNode("check_sufficiency", check_sufficiency_node),
            WorkflowNode("supplement", supplement_node, next_node="retrieve"),
            WorkflowNode("summarize", summarize_node),
            WorkflowNode("insufficient", insufficient_node),
        ],
        start_node="analyze",
        max_steps=max_steps,
    )


def build_workflow_context(
    model,
    collection,
    top_k: int | None = None,
    overrides: dict | None = None,
) -> dict:
    resolved_top_k = settings.top_k if top_k is None else top_k

    context = {
        "model": model,
        "collection": collection,
        "top_k": resolved_top_k,
        "max_supplement_attempts": settings.workflow_max_supplement_attempts,
        "max_summary_retries": settings.workflow_max_summary_retries,
        "search": lambda query, top_k: vector_search(
            query=query,
            model=model,
            collection=collection,
            top_k=top_k,
        ),
    }

    if overrides:
        context.update(overrides)

    return context


def run_knowledge_workflow(
    question: str,
    model,
    collection,
    state: AgentState | None = None,
    session_id: str | None = None,
    max_steps: int | None = None,
    context_overrides: dict | None = None,
) -> AgentState:
    """执行知识库检索、补充检索和总结生成的 Workflow。"""

    if state is None:
        state = AgentState.create(user_input=question, session_id=session_id)
    else:
        state.user_input = question

    state.add_message("user", question)
    context = build_workflow_context(
        model=model,
        collection=collection,
        overrides=context_overrides,
    )
    workflow = build_knowledge_workflow(max_steps=max_steps)

    return workflow.run(state, context)
