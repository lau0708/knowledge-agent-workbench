# Knowledge Agent Frontend

Vue 3 + TypeScript + Vite + Element Plus 实现的 AI 知识库 Agent 工作台。

## 页面

- `/dashboard`：系统概览
- `/knowledge-base`：知识库文档管理
- `/assistant`：RAG、Agent、Workflow、LangGraph 对话工作台
- `/workflow`：Workflow 执行轨迹
- `/approval`：HITL 人工审批
- `/trace`：Trace 监控与失败分析

## 启动

```bash
npm install
npm run dev
```

开发服务器默认运行在 `http://127.0.0.1:5173`，并将 `/api` 代理到 `http://127.0.0.1:8000`。

## 构建

```bash
npm run build
```
