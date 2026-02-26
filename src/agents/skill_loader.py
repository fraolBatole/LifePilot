"""Loader for agent skill files from the skills/ directory."""
import logging
from pathlib import Path

log = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def load_skill(filename: str) -> str:
    """Load a skill markdown file and return its contents."""
    path = SKILLS_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        log.warning("Skill file not found: %s", path)
        return ""


def build_system_prompt(base_prompt: str, agent_id: str) -> str:
    """Build a complete system prompt by combining the base prompt
    with the shared formatting skill and the agent-specific domain skill."""
    parts = [base_prompt]

    # Shared presentation skill (all agents)
    formatting = load_skill("telegram_formatting.md")
    if formatting:
        parts.append(formatting)

    # Agent-specific domain skill
    domain = load_skill(f"{agent_id}.md")
    if domain:
        parts.append(domain)

    return "\n\n---\n\n".join(parts)
