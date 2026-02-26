import os
from dotenv import load_dotenv

load_dotenv()

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
