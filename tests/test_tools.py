"""Smoke test for the tool registry and web search."""
import sys
sys.path.insert(0, "src")

from tools.registry import ToolRegistry, Tool
from tools.web_search import WEB_SEARCH_TOOL, _web_search


def test_tool_registry():
    reg = ToolRegistry()
    reg.register(WEB_SEARCH_TOOL)
    reg.set_permissions("nutrition", ["web_search"])
    reg.set_permissions("manager", [])

    # Nutrition gets web_search
    tools = reg.get_tools("nutrition")
    assert len(tools) == 1
    assert tools[0].name == "web_search"

    # Manager gets nothing
    tools = reg.get_tools("manager")
    assert len(tools) == 0

    # Unknown agent gets nothing
    tools = reg.get_tools("unknown")
    assert len(tools) == 0

    print("✅ ToolRegistry: PASS")


def test_schema_generation():
    schema = WEB_SEARCH_TOOL.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "web_search"
    assert "query" in schema["function"]["parameters"]["properties"]

    schema = WEB_SEARCH_TOOL.to_gemini_schema()
    assert schema["name"] == "web_search"

    schema = WEB_SEARCH_TOOL.to_anthropic_schema()
    assert schema["name"] == "web_search"
    assert "input_schema" in schema

    print("✅ Schema generation (OpenAI/Gemini/Claude): PASS")


def test_web_search_live():
    result = _web_search("Python programming language", max_results=3)
    assert "Python" in result or "python" in result
    assert len(result) > 50
    print(f"✅ Web search live test: PASS ({len(result)} chars returned)")
    print(f"   Preview: {result[:200]}...")


def test_tool_execute_via_registry():
    reg = ToolRegistry()
    reg.register(WEB_SEARCH_TOOL)
    result = reg.execute("web_search", query="what is magnesium", max_results=2)
    assert len(result) > 20
    print(f"✅ Registry.execute(): PASS")

    # Unknown tool
    result = reg.execute("nonexistent_tool", query="test")
    assert "Unknown tool" in result
    print(f"✅ Unknown tool error handling: PASS")


if __name__ == "__main__":
    test_tool_registry()
    test_schema_generation()
    test_web_search_live()
    test_tool_execute_via_registry()
    print("\n🎉 All smoke tests passed!")
