SUMMARIZE_PROMPT = """Summarize the following conversation between a user and an AI assistant.
Focus on: key topics discussed, decisions made, goals set, action items, and any personal information shared.
Be concise but preserve all important details. Write in third person about the user.

Conversation:
{conversation}"""

EXTRACT_FACTS_PROMPT = """Extract key facts from this conversation summary as a JSON array.
Each fact should have: "type" (goal/preference/milestone/habit), "key" (short label), "value" (detail).
Only extract facts that are clearly stated or strongly implied. Return [] if none found.

Summary:
{summary}

Return ONLY valid JSON array, no markdown fencing."""


class MemoryManager:
    def __init__(self, db, llm, summarize_threshold: int = 20):
        self.db = db
        self.llm = llm
        self.threshold = summarize_threshold

    def build_context(self, user_id: int, agent_id: str) -> list[dict]:
        """Assemble the full context window for an LLM call."""
        parts = []

        # Tier 4: User profile
        profile = self.db.get_profile(user_id, agent_id)
        if profile:
            parts.append(f"[User Profile]\n{_format_profile(profile)}")

        # Tier 3: Memory facts
        facts = self.db.get_facts(user_id, agent_id)
        if facts:
            parts.append(f"[Key Facts & Goals]\n{_format_facts(facts)}")

        # Tier 2: Recent summaries
        summaries = self.db.get_recent_summaries(user_id, agent_id, limit=3)
        if summaries:
            parts.append("[Previous Conversation Summaries]\n" +
                         "\n---\n".join(s["summary"] for s in summaries))

        context_block = "\n\n".join(parts)

        # Tier 1: Working memory (recent messages)
        messages = self.db.get_recent_messages(user_id, agent_id, limit=self.threshold)

        result = []
        if context_block:
            result.append({"role": "user", "content": f"[CONTEXT]\n{context_block}"})
            result.append({"role": "assistant", "content": "Understood. I have this context in mind."})
        result.extend({"role": m["role"], "content": m["content"]} for m in messages)
        return result

    async def maybe_summarize(self, user_id: int, agent_id: str):
        """Trigger summarization if unsummarized messages exceed threshold."""
        count, last_id = self.db.count_unsummarized_messages(user_id, agent_id)
        if count < self.threshold:
            return

        messages = self.db.get_messages_since(user_id, agent_id, last_id or 0)
        if not messages:
            return

        conversation = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
        summary = self.llm.chat(
            "You are a helpful summarizer.",
            [{"role": "user", "content": SUMMARIZE_PROMPT.format(conversation=conversation)}],
        )

        self.db.add_summary(
            user_id, agent_id, summary,
            msg_start_id=messages[0]["id"],
            msg_end_id=messages[-1]["id"],
        )

        # Extract facts from the summary
        try:
            import json
            facts_raw = self.llm.chat(
                "You extract structured facts from text.",
                [{"role": "user", "content": EXTRACT_FACTS_PROMPT.format(summary=summary)}],
            )
            facts = json.loads(facts_raw)
            for f in facts:
                self.db.upsert_fact(
                    user_id, agent_id,
                    f.get("type", "preference"),
                    f.get("key", ""),
                    f.get("value", ""),
                )
        except (json.JSONDecodeError, KeyError):
            pass  # best-effort fact extraction

    def get_session_summary(self, user_id: int, agent_id: str) -> str:
        """Generate a summary of recent conversations for the user."""
        summaries = self.db.get_recent_summaries(user_id, agent_id, limit=5)
        recent = self.db.get_recent_messages(user_id, agent_id, limit=10)

        if not summaries and not recent:
            return "No conversation history yet."

        parts = []
        if summaries:
            parts.append("Previous sessions:\n" + "\n---\n".join(s["summary"] for s in summaries))
        if recent:
            parts.append("Recent messages:\n" + "\n".join(
                f"{'You' if m['role'] == 'user' else 'Assistant'}: {m['content']}" for m in recent
            ))

        combined = "\n\n".join(parts)
        return self.llm.chat(
            "Summarize this conversation history for the user in a friendly, concise way. "
            "Highlight key topics, any goals or plans, and what was last discussed.",
            [{"role": "user", "content": combined}],
        )


def _format_profile(profile: dict) -> str:
    return "\n".join(f"- {k}: {v}" for k, v in profile.items())

def _format_facts(facts: list[dict]) -> str:
    return "\n".join(f"- [{f['fact_type']}] {f['fact_key']}: {f['fact_value']}" for f in facts)
