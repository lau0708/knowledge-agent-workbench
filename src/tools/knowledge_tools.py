from src.rag.retriever import search
from src.tools.registry import ToolRegistry


def register_knowledge_tools(
    registry: ToolRegistry,
    model,
    collection,
) -> None:
    """注册知识库检索工具。"""

    def search_knowledge_base(query: str, top_k: int = 3) -> dict:
        results = search(
            query=query,
            model=model,
            collection=collection,
            top_k=top_k,
        )

        return {
            "query": query,
            "count": len(results),
            "results": [
                {
                    "source": item["source"],
                    "score": round(item["score"], 4),
                    "content": item["content"][:1000],
                }
                for item in results
            ],
        }

    registry.register(
        name="search_knowledge_base",
        description="在本地知识库中按语义检索相关内容。",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "需要检索的问题或关键词",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回结果数量，默认 3",
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        handler=search_knowledge_base,
    )
