import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.agent.agent import run_agent
from src.agent.langgraph_workflow import run_langgraph_workflow
from src.agent.session import AgentSessionManager
from src.agent.state import AgentStatus, ToolCallStatus
from src.agent.workflow import run_knowledge_workflow
from src.config import settings
from src.database import db
from src.errors import AppError
from src.hitl.models import (
    HitlConflictError,
    HitlError,
    HitlExecutionError,
)
from src.hitl.service import HitlService
from src.logging_config import setup_logging
from src.memory.memory_service import MemoryService, init_memory_table
from src.observability import TraceStore, analyze_failure, build_trace
from src.rag.embedder import load_embedding_model
from src.rag.vector_store import get_collection
from src.services import document_service
from src.services.rag_service import ask
from src.tools import build_default_registry

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("初始化 SQLite 数据库...")
    db.init_db()
    init_memory_table()

    logger.info("正在加载 Embedding 模型...")
    app.state.model = load_embedding_model()

    logger.info("正在连接 ChromaDB...")
    app.state.collection = get_collection()

    logger.info("知识库服务初始化完成")
    logger.info("当前知识库数据量：%s", app.state.collection.count())

    yield

    logger.info("知识库服务正在关闭...")


app = FastAPI(
    title=settings.app_name,
    description="本地 RAG 知识库问答服务",
    version=settings.app_version,
    lifespan=lifespan,
)


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
            }
        },
    )


agent_session_manager = AgentSessionManager()
memory_service = MemoryService()
hitl_service = HitlService()
trace_store = TraceStore()


def _record_state_trace(state):
    trace = build_trace(state)
    trace_store.add(trace)
    return trace


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.warning(
        "业务异常 code=%s status=%s message=%s",
        exc.code,
        exc.status_code,
        exc.message,
    )
    return _error_response(exc.status_code, exc.code, exc.message)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code_map = {
        400: "BAD_REQUEST",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
    }
    return _error_response(
        exc.status_code,
        code_map.get(exc.status_code, "HTTP_ERROR"),
        str(exc.detail),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "请求参数校验失败",
                "detail": exc.errors(),
            }
        },
    )


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception):
    logger.exception("未处理异常", exc_info=exc)
    return _error_response(500, "INTERNAL_ERROR", "服务内部错误")


class ChatRequest(BaseModel):
    question: str


class DocumentUpdateRequest(BaseModel):
    content: str


class AgentChatRequest(BaseModel):
    question: str
    session_id: str | None = None


class ConfirmationApproveRequest(BaseModel):
    arguments: dict | None = None


class ConfirmationRejectRequest(BaseModel):
    reason: str | None = None


class ConfirmationModifyRequest(BaseModel):
    arguments: dict


@app.get("/")
def root():
    return {
        "message": "Local Knowledge Base API is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "local-knowledge-base",
    }


@app.post("/chat")
def chat(request: ChatRequest, http_request: Request):
    return ask(
        question=request.question,
        model=http_request.app.state.model,
        collection=http_request.app.state.collection,
    )


@app.post("/agent/chat")
def agent_chat(request: AgentChatRequest, http_request: Request):
    existing_state = None
    if request.session_id:
        existing_state = agent_session_manager.get(request.session_id)

    memory_context = memory_service.build_context_block(
        request.question,
        owner_id="default",
    )

    state = run_agent(
        question=request.question,
        model=http_request.app.state.model,
        collection=http_request.app.state.collection,
        state=existing_state,
        session_id=request.session_id,
        memory_context=memory_context,
        confirmation_service=hitl_service,
    )

    agent_session_manager.save(state)
    _record_state_trace(state)

    if state.status == AgentStatus.COMPLETED:
        memory_service.remember_turn(
            user_input=request.question,
            answer=state.answer or "",
            owner_id="default",
            session_id=request.session_id,
        )

    return state.to_dict()


@app.get("/agent/confirmations")
def list_confirmations(session_id: str | None = None):
    return [
        operation.to_dict()
        for operation in hitl_service.list_operations(session_id)
    ]


@app.get("/agent/confirmations/{operation_id}")
def get_confirmation(operation_id: str):
    operation = hitl_service.get_operation(operation_id)

    if operation is None:
        raise HTTPException(status_code=404, detail="待确认操作不存在")

    return operation.to_dict()


@app.post("/agent/confirmations/{operation_id}/modify")
def modify_confirmation(
    operation_id: str,
    payload: ConfirmationModifyRequest,
):
    try:
        operation = hitl_service.modify(operation_id, payload.arguments)
    except HitlConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except HitlError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return operation.to_dict()


@app.post("/agent/confirmations/{operation_id}/approve")
def approve_confirmation(
    operation_id: str,
    http_request: Request,
    payload: ConfirmationApproveRequest | None = None,
):
    registry = build_default_registry(
        http_request.app.state.model,
        http_request.app.state.collection,
    )

    try:
        operation = hitl_service.approve(
            operation_id,
            registry,
            modified_arguments=payload.arguments if payload else None,
        )
    except HitlConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except HitlExecutionError as exc:
        logger.warning("HITL 工具执行失败 operation=%s", operation_id)
        raise HTTPException(status_code=422, detail="工具执行失败")
    except HitlError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    state = agent_session_manager.get(operation.session_id)

    if state is not None:
        result = operation.result or ""
        state.add_message(
            "tool",
            result,
            tool_call_id=operation.tool_call_id,
        )
        state.resolve_tool_call(
            tool_call_id=operation.tool_call_id,
            result=result,
            status=ToolCallStatus.SUCCESS,
        )
        state.pending_operation_id = None

        resumed = run_agent(
            question=state.user_input,
            model=http_request.app.state.model,
            collection=http_request.app.state.collection,
            state=state,
            confirmation_service=hitl_service,
            resume=True,
        )
        agent_session_manager.save(resumed)
        _record_state_trace(resumed)
        return {
            "operation": operation.to_dict(),
            "state": resumed.to_dict(),
        }

    return {"operation": operation.to_dict()}


@app.post("/agent/confirmations/{operation_id}/reject")
def reject_confirmation(
    operation_id: str,
    payload: ConfirmationRejectRequest | None = None,
):
    try:
        operation = hitl_service.reject(
            operation_id,
            reason=payload.reason if payload else None,
        )
    except HitlConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except HitlError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    state = agent_session_manager.get(operation.session_id)

    if state is not None:
        error = operation.error or "用户拒绝执行"
        state.add_message(
            "tool",
            error,
            tool_call_id=operation.tool_call_id,
        )
        state.resolve_tool_call(
            tool_call_id=operation.tool_call_id,
            result=error,
            status=ToolCallStatus.FAILED,
            error=error,
        )
        state.pending_operation_id = None
        state.mark_failed(f"用户拒绝执行工具 {operation.tool_name}")
        agent_session_manager.save(state)
        _record_state_trace(state)
        return {
            "operation": operation.to_dict(),
            "state": state.to_dict(),
        }

    return {"operation": operation.to_dict()}


@app.post("/agent/workflow")
def agent_workflow(request: AgentChatRequest, http_request: Request):
    existing_state = None
    if request.session_id:
        existing_state = agent_session_manager.get(request.session_id)

    state = run_knowledge_workflow(
        question=request.question,
        model=http_request.app.state.model,
        collection=http_request.app.state.collection,
        state=existing_state,
        session_id=request.session_id,
    )

    agent_session_manager.save(state)
    _record_state_trace(state)
    return state.to_dict()


@app.post("/agent/langgraph")
def agent_langgraph(request: AgentChatRequest, http_request: Request):
    existing_state = None
    if request.session_id:
        existing_state = agent_session_manager.get(request.session_id)

    state = run_langgraph_workflow(
        question=request.question,
        model=http_request.app.state.model,
        collection=http_request.app.state.collection,
        state=existing_state,
        session_id=request.session_id,
    )

    agent_session_manager.save(state)
    _record_state_trace(state)
    return state.to_dict()


@app.get("/agent/traces")
def list_agent_traces(session_id: str | None = None):
    return [trace.to_dict() for trace in trace_store.list(session_id)]


@app.get("/agent/traces/{trace_id}")
def get_agent_trace(trace_id: str):
    trace = trace_store.get(trace_id)

    if trace is None:
        raise HTTPException(status_code=404, detail="Trace 不存在")

    return trace.to_dict()


@app.get("/agent/traces/{trace_id}/analysis")
def get_agent_trace_analysis(trace_id: str):
    trace = trace_store.get(trace_id)

    if trace is None:
        raise HTTPException(status_code=404, detail="Trace 不存在")

    return analyze_failure(trace)


@app.post("/documents", status_code=201)
async def upload_document(
    http_request: Request,
    file: UploadFile = File(...),
):
    content = await file.read()

    return document_service.create_document(
        collection=http_request.app.state.collection,
        filename=file.filename or "",
        content=content,
    )


@app.get("/documents")
def list_documents():
    return document_service.list_documents()


@app.get("/documents/{document_id}")
def get_document(document_id: int):
    return document_service.get_document(document_id)


@app.put("/documents/{document_id}")
def update_document(
    document_id: int,
    payload: DocumentUpdateRequest,
    http_request: Request,
):
    return document_service.update_document(
        collection=http_request.app.state.collection,
        document_id=document_id,
        content=payload.content,
    )


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    http_request: Request,
):
    return document_service.delete_document(
        collection=http_request.app.state.collection,
        document_id=document_id,
    )
