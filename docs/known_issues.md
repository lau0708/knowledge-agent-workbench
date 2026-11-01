# 已知限制

## 持久化与一致性

- Trace、HITL 待确认操作和 Agent Session 当前为进程内存储，服务重启后丢失。
- SQLite 与 ChromaDB 通过补偿机制同步，不是跨数据库强一致事务。
- 工具执行成功但进程在记录结果前崩溃时，缺少持久化执行状态和幂等机制。
- 原始 Markdown 丢失后，可从 SQLite/ChromaDB 恢复 Chunk 内容，但不能完整恢复原始文件。

## 文档格式

- 当前只支持 Markdown，不支持 PDF、Word、HTML 等格式。

## Memory

- 长期记忆当前使用关键词/BM25 检索，未使用 Embedding 向量检索。
- 记忆规则依赖关键词信号，无法覆盖复杂语义判断。

## 安全与权限

- 当前没有用户认证、多租户隔离和细粒度工具权限。
- 日志部分路径可能输出 traceback，尚未实现统一日志脱敏。
- HITL 只做高风险工具确认，不提供 RBAC 或审计级操作记录。

## 外部依赖

- 需要本地 `BAAI/bge-small-zh-v1.5` Embedding 模型。
- 需要可用的 DeepSeek API Key 和网络连接。

## 性能与规模

- 当前面向本地小规模知识库，未做大规模语料分片、分布式索引或异步任务队列。
- Agent Session 与 Trace 在内存中线性增长，长周期运行需要容量控制和清理策略。
