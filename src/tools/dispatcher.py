import json
import logging

from jsonschema import ValidationError, validate

from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolNotFoundError(Exception):
    """未注册的工具不能执行。"""


class ToolExecutionError(Exception):
    """工具执行失败。"""


class ToolArgumentError(ToolExecutionError):
    """工具参数校验失败。"""


class ToolDispatcher:
    """工具分发器：负责参数校验、执行工具并序列化结果。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def validate(self, name: str, arguments: dict):
        """只校验工具是否存在及参数是否合法，不执行工具。"""

        tool = self.registry.get(name)

        if tool is None:
            raise ToolNotFoundError(f"未注册的工具：{name}")

        if not isinstance(arguments, dict):
            raise ToolArgumentError("工具参数必须是 JSON 对象")

        try:
            validate(instance=arguments, schema=tool.parameters)
        except ValidationError as exc:
            raise ToolArgumentError(f"工具参数校验失败：{exc.message}") from exc

        return tool

    def dispatch(self, name: str, arguments: dict, tool_call_id: str | None = None) -> str:
        tool = self.validate(name, arguments)

        try:
            result = tool.handler(**arguments)
        except Exception as exc:
            logger.warning(
                "工具执行失败 tool=%s error_type=%s",
                name,
                type(exc).__name__,
            )
            raise ToolExecutionError("工具执行失败") from exc

        if isinstance(result, str):
            return result

        return json.dumps(result, ensure_ascii=False, default=str)
