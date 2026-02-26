from .base import BaseAgent

AGENT_NAMES = {
    "nutrition": "🥗 NutriBot",
    "fitness": "💪 FitBot",
    "finance": "💰 FinBot",
    "career": "🎯 CareerBot",
}


class ManagerAgent(BaseAgent):
    agent_id = "manager"
    name = "PilotManager"
    emoji = "🧠"
    system_prompt = (
        "You are PilotManager, the personal life oversight assistant. "
        "You have access to summaries and key facts from the user's nutrition, "
        "fitness, finance, and career conversations. Your job is to help them "
        "see the big picture, catch up on recent activity, and identify connections "
        "across life domains. Be insightful, concise, and encouraging."
    )

    def get_digest(self, user_id: int) -> str:
        all_summaries = self.db.get_all_agent_summaries(user_id)
        all_facts = self.db.get_all_facts(user_id)

        if not all_summaries and not all_facts:
            return (f"{self.emoji} No activity yet across your agents. "
                    "Start chatting with one of them to get going!")

        context = self._build_overview(all_summaries, all_facts)
        return self.llm.chat(
            self.system_prompt,
            [{"role": "user", "content":
              f"Here is an overview of the user's recent activity across all life domains:\n\n"
              f"{context}\n\n"
              f"Give a friendly, concise digest of what's been happening. "
              f"Highlight any progress, concerns, or actionable next steps."}],
        )

    def get_cross_insights(self, user_id: int) -> str:
        all_facts = self.db.get_all_facts(user_id)
        all_summaries = self.db.get_all_agent_summaries(user_id)

        if not all_facts and not all_summaries:
            return (f"{self.emoji} Not enough data yet for cross-domain insights. "
                    "Keep chatting with your agents!")

        context = self._build_overview(all_summaries, all_facts)
        return self.llm.chat(
            self.system_prompt,
            [{"role": "user", "content":
              f"Here is the user's data across all life domains:\n\n{context}\n\n"
              f"Identify interesting connections, synergies, or conflicts between "
              f"domains. For example, how their fitness and nutrition align, or how "
              f"spending patterns relate to career goals. Be specific and actionable."}],
        )

    def _build_overview(self, all_summaries: dict, all_facts: dict) -> str:
        parts = []
        for agent_id, label in AGENT_NAMES.items():
            section = [f"### {label}"]
            facts = all_facts.get(agent_id, [])
            if facts:
                section.append("Key facts:")
                for f in facts:
                    section.append(f"  - [{f['fact_type']}] {f['fact_key']}: {f['fact_value']}")
            summaries = all_summaries.get(agent_id, [])
            if summaries:
                section.append("Recent summaries:")
                for s in summaries:
                    section.append(f"  - {s['summary'][:200]}")
            if len(section) == 1:
                section.append("No activity yet.")
            parts.append("\n".join(section))
        return "\n\n".join(parts)
