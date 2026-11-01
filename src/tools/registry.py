from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Any]
    risk_level: str = "low"
    requires_confirmation: bool | None = None


class ToolRegistry:
    """工具注册表：只负责登记和查找工具，不负责执行。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
        handler: Callable[..., Any],
        risk_level: str = "low",
        requires_confirmation: bool | None = None,
    ) -> None:
        if not name or not name.strip():
            raise ValueError("工具名称不能为空")

        if name in self._tools:
            raise ValueError(f"工具已注册：{name}")

        self._tools[name] = Tool(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
            risk_level=risk_level,
            requires_confirmation=requires_confirmation,
        )

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def to_openai_schemas(self) -> list[dict]:
        """转换为 OpenAI 兼容的 tools 参数。"""

        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]
