from src.services import document_service
from src.tools.registry import ToolRegistry


def register_document_tools(registry: ToolRegistry, collection=None) -> None:
    """注册文档列表和详情工具。"""

    registry.register(
        name="list_documents",
        description="获取当前知识库中的文档列表。",
        parameters={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=lambda: {"documents": document_service.list_documents()},
    )

    registry.register(
        name="get_document",
        description="获取指定文档 ID 的详情和 Chunk 信息。",
        parameters={
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "integer",
                    "description": "文档 ID",
                },
            },
            "required": ["document_id"],
            "additionalProperties": False,
        },
        handler=lambda document_id: document_service.get_document(document_id),
    )

    if collection is not None:
        registry.register(
            name="delete_document",
            description="删除指定文档及其全部索引数据，该操作不可恢复。",
            parameters={
                "type": "object",
                "properties": {
                    "document_id": {
                        "type": "integer",
                        "description": "文档 ID",
                    },
                },
                "required": ["document_id"],
                "additionalProperties": False,
            },
            handler=lambda document_id: document_service.delete_document(
                collection,
                document_id,
            ),
            risk_level="high",
            requires_confirmation=True,
        )
