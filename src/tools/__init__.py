from src.tools.dispatcher import ToolDispatcher
from src.tools.document_tools import register_document_tools
from src.tools.knowledge_tools import register_knowledge_tools
from src.tools.registry import ToolRegistry


def build_default_registry(model, collection) -> ToolRegistry:
    """构建 Agent 默认工具注册表。"""

    registry = ToolRegistry()
    register_knowledge_tools(registry, model, collection)
    register_document_tools(registry, collection)
    return registry
