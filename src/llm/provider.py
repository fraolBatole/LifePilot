import os
import json
import logging
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

DEFAULTS = {
    "openai": "gpt-4o",
    "gemini": "gemini-flash-lite-latest",
    "claude": "claude-sonnet-4-20250514",
}


class LLMProvider:
    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "openai").lower()
        self.model = os.getenv("LLM_MODEL") or DEFAULTS.get(self.provider, "")
        self._client = None

    def _get_client(self):
        if self._client:
            return self._client

        if self.provider == "openai":
            from openai import OpenAI
            self._client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        elif self.provider == "gemini":
            from google import genai
            self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        elif self.provider == "claude":
            import anthropic
            self._client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")
        return self._client

    # ── Simple text chat (unchanged, used by memory/summarization) ───

    def chat(self, system_prompt: str, messages: list[dict]) -> str:
        """Send a chat completion request. messages = [{"role": ..., "content": ...}, ...]"""
        client = self._get_client()

        if self.provider == "openai":
            resp = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system_prompt}] + messages,
            )
            return resp.choices[0].message.content

        elif self.provider == "gemini":
            contents = []
            for m in messages:
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
            resp = client.models.generate_content(
                model=self.model,
                contents=contents,
                config={"system_instruction": system_prompt},
            )
            return resp.text

        elif self.provider == "claude":
            resp = client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=messages,
            )
            return resp.content[0].text

    # ── Chat with tool-calling (ReAct support) ───────────────────────

    def chat_with_tools(self, system_prompt: str, messages: list[dict],
                        tools: list) -> dict:
        """Send a chat request with tool definitions.

        Returns:
            {"type": "text", "content": "..."} for a final text answer, or
            {"type": "tool_call", "id": "...", "name": "...", "arguments": {...}}
            for a tool invocation request.
        """
        if not tools:
            # No tools — fall back to plain chat
            text = self.chat(system_prompt, messages)
            return {"type": "text", "content": text}

        client = self._get_client()

        if self.provider == "openai":
            return self._openai_tool_call(client, system_prompt, messages, tools)
        elif self.provider == "gemini":
            return self._gemini_tool_call(client, system_prompt, messages, tools)
        elif self.provider == "claude":
            return self._claude_tool_call(client, system_prompt, messages, tools)

    # ── OpenAI ───────────────────────────────────────────────────────

    def _openai_tool_call(self, client, system_prompt, messages, tools):
        tool_schemas = [t.to_openai_schema() for t in tools]
        resp = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}] + messages,
            tools=tool_schemas,
        )
        msg = resp.choices[0].message

        if msg.tool_calls:
            tc = msg.tool_calls[0]
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            return {
                "type": "tool_call",
                "id": tc.id,
                "name": tc.function.name,
                "arguments": args,
            }

        return {"type": "text", "content": msg.content or ""}

    # ── Gemini ───────────────────────────────────────────────────────

    def _gemini_tool_call(self, client, system_prompt, messages, tools):
        from google.genai import types

        # Build contents
        contents = []
        for m in messages:
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        # Build function declarations
        func_decls = []
        for t in tools:
            func_decls.append(types.FunctionDeclaration(
                name=t.name,
                description=t.description,
                parameters=t.parameters,
            ))
        gemini_tools = [types.Tool(function_declarations=func_decls)]

        resp = client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=gemini_tools,
            ),
        )

        # Check for function call in parts
        for part in resp.candidates[0].content.parts:
            if part.function_call:
                fc = part.function_call
                return {
                    "type": "tool_call",
                    "id": fc.name,  # Gemini doesn't use separate IDs
                    "name": fc.name,
                    "arguments": dict(fc.args) if fc.args else {},
                }

        return {"type": "text", "content": resp.text or ""}

    # ── Claude ───────────────────────────────────────────────────────

    def _claude_tool_call(self, client, system_prompt, messages, tools):
        tool_schemas = [t.to_anthropic_schema() for t in tools]
        resp = client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
            tools=tool_schemas,
        )

        # Claude can return mixed content blocks
        for block in resp.content:
            if block.type == "tool_use":
                return {
                    "type": "tool_call",
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input or {},
                }

        # Text response
        text_parts = [b.text for b in resp.content if b.type == "text"]
        return {"type": "text", "content": "\n".join(text_parts)}
