"""Tool registry for the ReAct agent loop."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)


@dataclass
class Tool:
    """A single tool that an agent can invoke."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the input
    function: Callable[..., str] = field(repr=False)

    def execute(self, **kwargs) -> str:
        try:
            return self.function(**kwargs)
        except Exception as e:
            log.error("Tool %s failed: %s", self.name, e)
            return f"Error executing {self.name}: {e}"

    # ── Provider-specific schema converters ──────────────────────────

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def to_gemini_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def to_anthropic_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


class ToolRegistry:
    """Holds all registered tools and controls per-agent access."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}
        # agent_id -> list of tool names the agent can use
        self._permissions: dict[str, list[str]] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def set_permissions(self, agent_id: str, tool_names: list[str]) -> None:
        self._permissions[agent_id] = tool_names

    def get_tools(self, agent_id: str) -> list[Tool]:
        allowed = self._permissions.get(agent_id, [])
        return [self._tools[n] for n in allowed if n in self._tools]

    def execute(self, tool_name: str, **kwargs) -> str:
        tool = self._tools.get(tool_name)
        if not tool:
            return f"Unknown tool: {tool_name}"
        return tool.execute(**kwargs)
