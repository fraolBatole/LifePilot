import logging

from agents.skill_loader import build_system_prompt

log = logging.getLogger(__name__)

MAX_REACT_STEPS = 5  # Safety cap to prevent infinite loops


class BaseAgent:
    agent_id: str = ""
    name: str = ""
    emoji: str = ""
    system_prompt: str = ""

    def __init__(self, db, llm, memory, tool_registry=None):
        self.db = db
        self.llm = llm
        self.memory = memory
        self.tool_registry = tool_registry
        # Build enriched prompt: base + formatting skill + domain skill
        self._full_prompt = build_system_prompt(self.system_prompt, self.agent_id)

    def get_greeting(self) -> str:
        return f"{self.emoji} Hey! I'm {self.name}. What would you like to talk about?"

    async def handle_message(self, user_id: int, text: str) -> str:
        self.db.add_message(user_id, self.agent_id, "user", text)
        context = self.memory.build_context(user_id, self.agent_id)

        # Get tools available to this agent
        tools = []
        if self.tool_registry:
            tools = self.tool_registry.get_tools(self.agent_id)

        if not tools:
            # No tools — simple single-shot (backward-compatible path)
            response = self.llm.chat(self._full_prompt, context)
            self.db.add_message(user_id, self.agent_id, "assistant", response)
            await self.memory.maybe_summarize(user_id, self.agent_id)
            return response

        # ── ReAct Loop ───────────────────────────────────────────────
        for step in range(MAX_REACT_STEPS):
            result = self.llm.chat_with_tools(self._full_prompt, context, tools)

            if result["type"] == "text":
                # Final answer
                response = result["content"]
                self.db.add_message(user_id, self.agent_id, "assistant", response)
                await self.memory.maybe_summarize(user_id, self.agent_id)
                return response

            # Tool call — execute and feed observation back into context
            tool_name = result["name"]
            tool_args = result["arguments"]
            log.info("Agent %s calling tool: %s(%s)", self.agent_id, tool_name, tool_args)

            observation = self.tool_registry.execute(tool_name, **tool_args)
            log.info("Tool %s returned %d chars", tool_name, len(observation))

            # Append the tool call + observation to the conversation context
            # so the LLM sees what happened and can reason about it.
            context.append({
                "role": "assistant",
                "content": f"[Calling tool: {tool_name}]\nArguments: {tool_args}",
            })
            context.append({
                "role": "user",
                "content": (
                    f"[Tool Result from {tool_name}]\n{observation}\n\n"
                    "Use this information to answer the user's question. "
                    "If you need more information, you can call another tool. "
                    "Otherwise, provide your final answer."
                ),
            })

        # Exhausted all steps without a final answer
        fallback = (
            "I did some research but wasn't able to fully answer your question. "
            "Here's what I found so far — could you try rephrasing or narrowing down your question?"
        )
        self.db.add_message(user_id, self.agent_id, "assistant", fallback)
        return fallback

    def get_summary(self, user_id: int) -> str:
        return self.memory.get_session_summary(user_id, self.agent_id)

    def get_continue_greeting(self, user_id: int) -> str:
        recent = self.db.get_recent_messages(user_id, self.agent_id, limit=3)
        if not recent:
            return self.get_greeting()
        last_topic = recent[-1]["content"][:100]
        return (f"{self.emoji} Welcome back! Last time we were discussing:\n"
                f"_{last_topic}..._\n\nWant to continue, or start something new?")
