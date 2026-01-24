from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass(frozen=True)
class ClaudeConfig:
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 768
    temperature: float = 0.7


class ClaudeStreamingClient(QObject):
    text_chunk = pyqtSignal(str)
    response_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    CONTEXT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context.txt")

    def __init__(self, config: Optional[ClaudeConfig] = None) -> None:
        super().__init__()
        self._config = config or ClaudeConfig()
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._client: Optional[Anthropic] = None
        self._context = self._load_context()

    def _load_context(self) -> str:
        try:
            with open(self.CONTEXT_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def _build_system_prompt(self) -> str:
        base_instruction = """You are ME in a technical interview. You have access to my resume above. Speak as if YOU lived these experiences.

CRITICAL RULES:
- First-person answers ONLY. Say "I built..." not "You could say you built..."
- Lead with the answer. No preamble like "Great question!"
- Keep explanations to 2-3 sentences max.

FOR BEHAVIORAL QUESTIONS ("Tell me about a time..."):
- Search my resume for relevant experience and use STAR format (Situation, Task, Action, Result)
- Use specific details: team sizes, technologies, metrics, outcomes
- If no exact match, bridge to the closest related experience I have

FOR TECHNICAL QUESTIONS I LACK EXPERIENCE IN:
- Give me a concise explanation of the concept (so I sound knowledgeable)
- Then suggest how to bridge: "I haven't implemented X directly, but in my work on [related thing from resume], I used similar principles..."
- Help me sound competent without lying

FOR SYSTEM DESIGN / CODING:
- Use markdown code blocks with language tags
- Add brief inline comments on non-obvious lines
- Include time/space complexity when relevant (e.g., O(n) time, O(1) space)
- Prefer readability over cleverness

TONE: Confident peer, not arrogant lecturer. No hedging phrases like "I think maybe..."."""
        if self._context:
            return f"{self._context}\n\n---\n\n{base_instruction}"
        return base_instruction

    def _ensure_client(self) -> bool:
        if not self._api_key:
            self.error_occurred.emit("ANTHROPIC_API_KEY not set")
            return False
        if not self._client:
            self._client = Anthropic(api_key=self._api_key)
        return True

    async def stream_response(self, question: str) -> None:
        if not self._ensure_client():
            return

        try:
            with self._client.messages.stream(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                system=self._build_system_prompt(),
                messages=[{"role": "user", "content": question}],
            ) as stream:
                for text in stream.text_stream:
                    self.text_chunk.emit(text)

            self.response_complete.emit()

        except Exception as e:
            self.error_occurred.emit(f"Claude error: {e}")

    async def stream_vision_response(self, prompt: str, image_path: str) -> None:
        if not self._ensure_client():
            return

        try:
            with open(image_path, "rb") as f:
                image_data = base64.standard_b64encode(f.read()).decode("utf-8")

            with self._client.messages.stream(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }],
            ) as stream:
                for text in stream.text_stream:
                    self.text_chunk.emit(text)

            self.response_complete.emit()

        except Exception as e:
            self.error_occurred.emit(f"Claude vision error: {e}")
