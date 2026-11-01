# 测试矩阵

## 自动化回归门禁

以下两类测试不依赖真实 Embedding 模型和 DeepSeek API，可作为 CI 或提交前回归门禁。

| 类别 | 范围 | 命令 | 说明 |
| --- | --- | --- | --- |
| 单元测试 | `tests/unit/` | `python run_tests.py --unit` | 覆盖 Agent、State、Workflow、LangGraph、Tools、HITL、Memory、API、RAG Service 等。 |
| 集成测试 | `tests/test_indexing_service.py` | `python run_tests.py --integration` | 使用临时 SQLite 和 Ephemeral ChromaDB，验证双存储同步、更新、删除、补偿与一致性。 |
| 全量回归 | 单元 + 集成 | `python run_tests.py` | 默认执行完整自动化门禁。 |

## 真实数据冒烟与验收

以下命令会读写真实 `data/`，需要本地 Embedding 模型或真实 DeepSeek API，不纳入 `run_tests.py`。

| 命令 | 用途 |
| --- | --- |
| `python -m tests.test_indexing_service --verify` | 检查真实 SQLite 与 ChromaDB 是否一致。 |
| `python -m tests.test_indexing_service --real` | 从 `data/documents` 重新构建并同步索引。 |
| `python -m tests.test_storage_status` | 查看真实 SQLite 与 ChromaDB 的文档和 Chunk 数量。 |
| `python -m tests.test_bm25` | 使用真实索引验证 BM25 检索。 |
| `python -m tests.test_retriever_chroma` | 使用真实向量索引验证 ChromaDB 检索。 |
| `python -m tests.test_vector_store` | 验证向量写入与检索的简单链路。 |
| `python -m tests.test_generation_evaluator` | 调用 DeepSeek 验证生成质量评估。 |

## 分类原则

- 单元测试：隔离在单模块或单服务内，使用 mock、临时文件和 Ephemeral 存储。
- 集成测试：跨 SQLite 与 ChromaDB 两个真实依赖，但数据仍使用临时目录隔离。
- 回归测试：由上述单元测试和集成测试共同构成固定质量门禁。
- 冒烟测试：依赖真实模型、真实数据或真实 API，只在验收阶段手动执行。
