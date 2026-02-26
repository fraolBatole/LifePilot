class BaseAgent:
    agent_id: str = ""
    name: str = ""
    emoji: str = ""
    system_prompt: str = ""

    def __init__(self, db, llm, memory):
        self.db = db
        self.llm = llm
        self.memory = memory

    def get_greeting(self) -> str:
        return f"{self.emoji} Hey! I'm {self.name}. What would you like to talk about?"

    async def handle_message(self, user_id: int, text: str) -> str:
        self.db.add_message(user_id, self.agent_id, "user", text)
        context = self.memory.build_context(user_id, self.agent_id)
        response = self.llm.chat(self.system_prompt, context)
        self.db.add_message(user_id, self.agent_id, "assistant", response)
        await self.memory.maybe_summarize(user_id, self.agent_id)
        return response

    def get_summary(self, user_id: int) -> str:
        return self.memory.get_session_summary(user_id, self.agent_id)

    def get_continue_greeting(self, user_id: int) -> str:
        recent = self.db.get_recent_messages(user_id, self.agent_id, limit=3)
        if not recent:
            return self.get_greeting()
        last_topic = recent[-1]["content"][:100]
        return (f"{self.emoji} Welcome back! Last time we were discussing:\n"
                f"_{last_topic}..._\n\nWant to continue, or start something new?")
