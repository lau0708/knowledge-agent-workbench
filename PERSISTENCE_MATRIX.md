# 持久化边界矩阵

## 结论

| 数据 | 当前实现 | 是否跨进程重启保留 | 风险 | 建议 |
| --- | --- | --- | --- | --- |
| SQLite 文档/Chunk | `src/database/db.py` 文件数据库 | 是 | 无 | 保持现状 |
| ChromaDB 向量 | `src/rag/vector_store.py` PersistentClient | 是 | 可由 Markdown 重建 | 保持现状 |
| Memory 长期记忆 | `src/memory/memory_store.py` SQLite `memories` 表 | 是 | 无 | 保持现状 |
| Trace | `src/observability/tracing.py` `TraceStore` 进程内 dict | 否 | 服务重启后近期 Trace 全部丢失 | 如需跨重启可观测性，应迁入 SQLite |
| HITL 待确认操作 | `src/hitl/store.py` `PendingOperationStore` 进程内 dict | 否 | 服务重启后待确认操作全部丢失；已批准但未记录结果仍可能重复/悬空 | 如需生产级 HITL，应持久化状态并引入幂等执行记录 |

## 边界说明

- SQLite、ChromaDB、Memory 使用文件或目录持久化，服务重启后数据仍在。
- Trace 当前定位是“最近执行记录”，不是审计级存储，因此进程内实现符合 S7 的简化目标。
- HITL 的 `PendingOperationStore` 是进程内存储，重启后无法恢复 `pending/approved` 中间状态。
- Agent Session 同样由 `AgentSessionManager` 在进程内维护，未纳入本轮五类数据，但属于相邻边界，后续持久化时需一并考虑。

## 已固化测试

`tests/unit/test_persistence_boundaries.py` 验证：

- Memory 在相同 SQLite 文件的新连接中仍可读取。
- TraceStore 的新实例无法读取旧实例数据。
- PendingOperationStore 的新实例无法读取旧实例数据。

这组测试用于锁定当前边界，防止未来误把进程内存储当作持久化存储。
