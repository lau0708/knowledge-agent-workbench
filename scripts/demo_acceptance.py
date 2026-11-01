#!/usr/bin/env python3
"""离线验收演示：使用临时 SQLite/ChromaDB 和 mock LLM 走核心链路。"""

import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

import chromadb
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import main
from src.agent.state import AgentState
from src.database import db
from src.hitl.models import ConfirmationRequiredError
from src.hitl.service import HitlService
from src.services import document_service
from src.services.indexing_service import sync_document_chunks
from src.tools.registry import ToolRegistry


def section(title: str) -> None:
    print(f"\n===== {title} =====")


def fake_sync_file(collection, source, chunk_size=None, chunk_overlap=None):
    content = Path(source).read_text(encoding="utf-8")
    return sync_document_chunks(
        collection,
        source,
        [
            {
                "chunk_id": f"{Path(source).stem}_0",
                "source": source,
                "chunk_index": 0,
                "content": content[:40],
                "embedding": [0.1] * 8,
            }
        ],
    )


def fake_ask(question, model, collection, top_k=None):
    return {
        "question": question,
        "context": [],
        "answer": f"演示回答：{question}",
        "evaluation": None,
    }


def fake_run_agent(
    question,
    model,
    collection,
    state=None,
    session_id=None,
    memory_context=None,
    confirmation_service=None,
    resume=False,
):
    state = state or AgentState.create(question, session_id=session_id)
    state.user_input = question
    state.mark_completed(f"演示 Agent 回答：{question}")
    return state


def fake_run_workflow(question, model, collection, state=None, session_id=None):
    state = state or AgentState.create(question, session_id=session_id)
    state.user_input = question
    state.add_workflow_event("summarize", "completed")
    state.mark_completed("演示 Workflow 总结")
    return state


def run_api_demo() -> None:
    tempdir = tempfile.TemporaryDirectory()
    old_db_path = db.DB_PATH
    old_docs_dir = document_service.DOCUMENTS_DIR
    old_load_model = main.load_embedding_model
    old_get_collection = main.get_collection

    db.DB_PATH = Path(tempdir.name) / "demo.db"
    db.init_db()
    document_service.DOCUMENTS_DIR = Path(tempdir.name) / "docs"

    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        name=f"demo_{uuid.uuid4().hex}",
        metadata={"hnsw:space": "cosine"},
    )

    try:
        with patch.object(main, "load_embedding_model", return_value=object()), patch.object(
            main, "get_collection", return_value=collection
        ), patch.object(main, "ask", side_effect=fake_ask), patch.object(
            main, "run_agent", side_effect=fake_run_agent
        ), patch.object(
            main, "run_knowledge_workflow", side_effect=fake_run_workflow
        ), patch.object(
            main, "run_langgraph_workflow", side_effect=fake_run_workflow
        ), patch.object(
            document_service, "sync_file", side_effect=fake_sync_file
        ):
            with TestClient(main.app) as api:
                section("健康检查")
                health = api.get("/health")
                print(health.status_code, health.json())

                section("文档生命周期")
                upload = api.post(
                    "/documents",
                    files={"file": ("demo.md", b"# Demo Document", "text/markdown")},
                )
                print("upload", upload.status_code, upload.json()["id"])
                document_id = upload.json()["id"]

                listing = api.get("/documents")
                print("list", listing.status_code, len(listing.json()))

                detail = api.get(f"/documents/{document_id}")
                print("detail", detail.status_code, detail.json()["source"])

                update = api.put(
                    f"/documents/{document_id}",
                    json={"content": "# Updated Demo"},
                )
                print("update", update.status_code, update.json()["chunks"][0]["content"])

                delete = api.delete(f"/documents/{document_id}")
                print("delete", delete.status_code, delete.json()["deleted"])

                section("知识库问答")
                chat = api.post("/chat", json={"question": "什么是 RAG？"})
                print("chat", chat.status_code, chat.json()["answer"])

                section("Agent 会话状态")
                agent_first = api.post(
                    "/agent/chat",
                    json={"question": "第一轮", "session_id": "demo-session"},
                )
                agent_second = api.post(
                    "/agent/chat",
                    json={"question": "第二轮", "session_id": "demo-session"},
                )
                print("agent_1", agent_first.status_code, agent_first.json()["answer"])
                print(
                    "agent_2",
                    agent_second.status_code,
                    len(agent_second.json()["messages"]),
                )

                section("Workflow")
                workflow = api.post(
                    "/agent/workflow",
                    json={"question": "整理 RAG 资料", "session_id": "workflow-demo"},
                )
                print("workflow", workflow.status_code, workflow.json()["answer"])

                section("LangGraph")
                langgraph = api.post(
                    "/agent/langgraph",
                    json={"question": "LangGraph 链路", "session_id": "graph-demo"},
                )
                print("langgraph", langgraph.status_code, langgraph.json()["answer"])

                section("Trace")
                traces = api.get("/agent/traces", params={"session_id": "demo-session"})
                print("traces", traces.status_code, len(traces.json()))
    finally:
        main.get_collection = old_get_collection
        main.load_embedding_model = old_load_model
        document_service.DOCUMENTS_DIR = old_docs_dir
        db.DB_PATH = old_db_path
        tempdir.cleanup()


def run_hitl_demo() -> None:
    section("HITL 高风险工具")
    calls = []
    registry = ToolRegistry()
    registry.register(
        "delete_document",
        "删除指定文档，操作不可恢复。",
        {
            "type": "object",
            "properties": {"document_id": {"type": "integer"}},
            "required": ["document_id"],
            "additionalProperties": False,
        },
        lambda document_id: calls.append(document_id) or {"deleted": document_id},
        risk_level="high",
    )

    service = HitlService()
    try:
        service.dispatch(registry, "delete_document", {"document_id": 1}, session_id="demo")
    except ConfirmationRequiredError as exc:
        print("pending", exc.operation_id)
        operation_id = exc.operation_id

    operation = service.approve(operation_id, registry)
    print("approved", operation.status.value, calls)


def main_script() -> int:
    run_api_demo()
    run_hitl_demo()
    print("\n演示完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main_script())
