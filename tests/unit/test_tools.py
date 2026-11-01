import unittest

from src.tools.dispatcher import (
    ToolArgumentError,
    ToolDispatcher,
    ToolExecutionError,
    ToolNotFoundError,
)
from src.tools.registry import ToolRegistry


class ToolRegistryAndDispatcherTest(unittest.TestCase):
    def setUp(self):
        self.registry = ToolRegistry()

    def test_register_and_openai_schema(self):
        self.registry.register(
            name="echo",
            description="回显输入",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
                "additionalProperties": False,
            },
            handler=lambda text: {"text": text},
        )

        self.assertEqual(self.registry.names(), ["echo"])
        schemas = self.registry.to_openai_schemas()
        self.assertEqual(schemas[0]["function"]["name"], "echo")

    def test_duplicate_tool_is_rejected(self):
        self.registry.register("echo", "a", {"type": "object", "properties": {}}, lambda: None)

        with self.assertRaises(ValueError):
            self.registry.register("echo", "b", {"type": "object", "properties": {}}, lambda: None)

    def test_dispatch_valid_tool(self):
        self.registry.register(
            "add",
            "加法",
            {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
            lambda a, b: {"sum": a + b},
        )

        dispatcher = ToolDispatcher(self.registry)
        result = dispatcher.dispatch("add", {"a": 1, "b": 2})
        self.assertIn('"sum": 3', result)

    def test_unregistered_tool_cannot_execute(self):
        dispatcher = ToolDispatcher(self.registry)

        with self.assertRaises(ToolNotFoundError):
            dispatcher.dispatch("not_exists", {})

    def test_invalid_arguments_are_rejected(self):
        self.registry.register(
            "add",
            "加法",
            {
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
                "additionalProperties": False,
            },
            lambda a, b: a + b,
        )

        dispatcher = ToolDispatcher(self.registry)

        with self.assertRaises(ToolArgumentError):
            dispatcher.dispatch("add", {"a": 1})

    def test_handler_exception_is_wrapped(self):
        def broken():
            raise RuntimeError("boom")

        self.registry.register(
            "broken",
            "异常工具",
            {"type": "object", "properties": {}},
            broken,
        )

        dispatcher = ToolDispatcher(self.registry)

        with self.assertRaises(ToolExecutionError):
            dispatcher.dispatch("broken", {})


if __name__ == "__main__":
    unittest.main()
