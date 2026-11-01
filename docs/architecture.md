# 系统架构

## 总览

```mermaid
flowchart TB
    Client[Vue 3 Web 工作台 / Swagger UI] --> API[FastAPI src/main.py]

    API --> Documents[文档管理 /documents]
    API --> Chat[RAG 问答 /chat]
    API --> Agent[Agent 入口 /agent/chat]
    API --> Workflow[Workflow /agent/workflow]
    API --> Graph[LangGraph /agent/langgraph]

    Documents --> DocService[document_service]
    Documents --> Indexing[indexing_service]
    Indexing --> SQLite[(SQLite)]
    Indexing --> Chroma[(ChromaDB)]

    Chat --> RAGService[rag_service]
    RAGService --> Retriever[Hybrid Retriever]
    Retriever --> Chroma
    RAGService --> LLM[DeepSeek]

    Agent --> State[AgentState / Session]
    Agent --> Tools[Tool Registry / Dispatcher]
    Agent --> HITL[HITL Service]
    Agent --> Memory[Memory Service]
    Agent --> LLM
    Tools --> DocService
    Tools --> Chroma
    HITL --> Tools
    Memory --> SQLite

    Workflow --> State
    Workflow --> Retriever
    Workflow --> LLM
    Graph --> State
    Graph --> Retriever
    Graph --> LLM

    API --> Trace[Trace Store]
    State --> Trace
```

## 分层职责

| 层 | 模块 | 职责 |
| --- | --- | --- |
| 展示层 | `frontend/` | Vue 3 + Element Plus，六页知识库 Agent 工作台。 |
| 接入层 | `src/main.py` | 路由、统一异常处理、应用生命周期。 |
| 执行层 | `src/agent/agent.py` | Agent Loop、工具调用循环、状态更新。 |
| 执行层 | `src/agent/workflow.py` | 手写节点、条件路由和有限循环。 |
| 执行层 | `src/agent/langgraph_workflow.py` | LangGraph 对照实现。 |
| 能力层 | `src/services/rag_service.py` | RAG 检索、生成和评估编排。 |
| 能力层 | `src/tools/` | 工具注册、参数校验、执行分发。 |
| 能力层 | `src/hitl/` | 高风险操作确认、批准、拒绝和超时。 |
| 能力层 | `src/memory/` | 短期历史裁剪和长期记忆存取。 |
| 数据层 | `src/database/db.py` | SQLite 文档、Chunk、Memory。 |
| 数据层 | `src/rag/vector_store.py` | ChromaDB 向量持久化。 |
| 外部依赖 | `src/rag/llm.py`、`src/rag/embedder.py` | DeepSeek 生成、本地 Embedding。 |

## 关键链路

### 知识库问答

```mermaid
sequenceDiagram
    participant Client
    participant API as /chat
    participant RAG as rag_service
    participant Search as Hybrid Retriever
    participant Chroma
    participant DeepSeek

    Client->>API: POST /chat
    API->>RAG: ask(question, model, collection)
    RAG->>Search: search(query)
    Search->>Chroma: vector + BM25
    Chroma-->>Search: chunks
    Search-->>RAG: ranked chunks
    RAG->>DeepSeek: generate answer
    DeepSeek-->>RAG: answer
    RAG-->>API: answer + context + evaluation
    API-->>Client: JSON
```

### Agent 工具调用

```mermaid
sequenceDiagram
    participant Client
    participant API as /agent/chat
    participant Agent
    participant Tool
    participant HITL
    participant State
    participant Trace

    Client->>API: POST /agent/chat
    API->>Agent: run_agent
    Agent->>Tool: dispatch
    alt 高风险工具
        Tool->>HITL: 创建待确认操作
        HITL-->>Agent: WAITING_CONFIRMATION
        Agent-->>State: 保存 pending_operation_id
    else 普通工具
        Tool-->>Agent: 执行结果
    end
    Agent-->>API: AgentState
    API->>Trace: build_trace + add
    API-->>Client: state JSON
```

## 目录结构

```text
src/
├── agent/          # Agent、State、Workflow、LangGraph
├── database/       # SQLite
├── errors.py       # 业务异常
├── hitl/           # Human-in-the-loop
├── memory/         # 短期与长期记忆
├── observability/  # Trace、评估、失败分析
├── rag/            # 文档、切分、Embedding、检索、LLM
├── services/       # 文档与索引服务
└── tools/          # 工具注册与分发
```
