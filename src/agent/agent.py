import json
import logging

from src.agent.state import AgentState, AgentStatus, ToolCallStatus
from src.config import settings
from src.hitl.models import ConfirmationRequiredError
from src.memory.short_term import trim_messages
from src.rag.llm import chat_deepseek
from src.tools import build_default_registry
from src.tools.dispatcher import (
    ToolDispatcher,
    ToolExecutionError,
    ToolNotFoundError,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是本地知识库助手。

你可以使用提供的工具查询知识库和文档信息。请遵循以下规则：
1. 对问候、闲聊或不需要外部信息的任务，直接回答，不调用工具。
2. 需要知识库内容时，使用 search_knowledge_base。
3. 需要查看文档列表或详情时，使用 list_documents 或 get_document。
4. 只能使用已注册的工具，不要虚构工具名称。
5. 如果工具返回错误，可以尝试修正参数；若仍无法完成，请如实说明。
"""


def run_agent(
    question: str,
    model,
    collection,
    max_tool_calls: int | None = None,
    state: AgentState | None = None,
    session_id: str | None = None,
    memory_context: str | None = None,
    confirmation_service=None,
    resume: bool = False,
) -> AgentState:
    """执行 Agent 任务，并持续更新 AgentState。"""

    max_tool_calls = settings.agent_max_tool_calls if max_tool_calls is None else max_tool_calls

    if state is None:
        state = AgentState.create(user_input=question, session_id=session_id)
    elif not resume:
        state.user_input = question

    state.start()

    if not resume:
        if not state.messages:
            system_content = SYSTEM_PROMPT
            if memory_context:
                system_content = f"{SYSTEM_PROMPT}\n\n{memory_context}"

            state.add_message("system", system_content)
            state.add_message("user", question)
        else:
            state.add_message("user", question)

        state.messages = trim_messages(
            state.messages,
            max_messages=settings.short_term_memory_max_messages,
        )

    registry = build_default_registry(model, collection)
    dispatcher = (
        confirmation_service.build_dispatcher(registry, state.session_id)
        if confirmation_service is not None
        else ToolDispatcher(registry)
    )

    rounds = 0

    while rounds < max_tool_calls:
        try:
            response = chat_deepseek(
                messages=state.messages,
                tools=registry.to_openai_schemas(),
            )
        except Exception as exc:
            logger.exception("模型调用失败")
            state.mark_failed(f"模型调用失败：{exc}")
            return state

        content = response.get("content") or ""
        tool_calls = response.get("tool_calls") or []

        if not tool_calls:
            final_answer = content or "模型未返回有效内容"
            state.add_message("assistant", final_answer)
            state.mark_completed(final_answer)
            return state

        rounds += 1
        state.add_message("assistant", content, tool_calls=tool_calls)

        for tool_call in tool_calls:
            function = tool_call.get("function") or {}
            name = function.get("name", "")
            arguments_text = function.get("arguments") or "{}"
            tool_call_id = tool_call.get("id") or f"call_{state.tool_call_count}"

            try:
                arguments = json.loads(arguments_text)
                if not isinstance(arguments, dict):
                    raise ValueError("参数必须是 JSON 对象")
            except Exception as exc:
                arguments = {}
                result = json.dumps(
                    {"error": f"工具参数解析失败：{exc}"},
                    ensure_ascii=False,
                )
                tool_status = ToolCallStatus.FAILED
                tool_error = str(exc)
            else:
                try:
                    result = dispatcher.dispatch(
                        name,
                        arguments,
                        tool_call_id=tool_call_id,
                    )
                    tool_status = ToolCallStatus.SUCCESS
                    tool_error = None
                except ConfirmationRequiredError as exc:
                    state.pending_operation_id = exc.operation_id
                    state.add_tool_call(
                        name=name,
                        arguments=arguments,
                        result="",
                        status=ToolCallStatus.WAITING_CONFIRMATION,
                        tool_call_id=tool_call_id,
                    )
                    state.status = AgentStatus.WAITING_CONFIRMATION
                    logger.info(
                        "工具等待确认 tool=%s operation_id=%s",
                        name,
                        exc.operation_id,
                    )
                    return state
                except ToolNotFoundError as exc:
                    result = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    tool_status = ToolCallStatus.FAILED
                    tool_error = str(exc)
                except ToolExecutionError as exc:
                    result = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    tool_status = ToolCallStatus.FAILED
                    tool_error = str(exc)
                except Exception as exc:
                    logger.warning(
                        "工具分发异常 tool=%s error_type=%s",
                        name,
                        type(exc).__name__,
                    )
                    result = json.dumps(
                        {"error": "工具执行异常"},
                        ensure_ascii=False,
                    )
                    tool_status = ToolCallStatus.FAILED
                    tool_error = "工具执行异常"

            state.add_message("tool", result, tool_call_id=tool_call_id)
            state.add_tool_call(
                name=name,
                arguments=arguments,
                result=result,
                status=tool_status,
                error=tool_error,
                tool_call_id=tool_call_id,
            )

            logger.info(
                "工具调用 tool=%s arguments=%s status=%s",
                name,
                arguments,
                tool_status.value,
            )

    state.mark_failed("已达到最大工具调用轮数，任务未完成。")
    return state
