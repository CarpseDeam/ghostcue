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

CRITICAL: THIS IS A VERBAL INTERVIEW - I will be SPEAKING your response out loud.
- NO CODE BLOCKS. Never. I cannot recite code verbally.
- Explain concepts conversationally, like you're talking to the interviewer
- For system design: describe components, data flow, trade-offs in plain English
- A one-liner pseudocode reference is okay ("I'd use a dictionary mapping user IDs to timestamps")
- Keep responses under 30 seconds of speaking time (~75-100 words)

RESPONSE RULES:
- First-person ONLY. Say "I built..." not "You could say..."
- Lead with the answer. No preamble like "Great question!"
- Be concise. Interviewers can ask follow-ups.

FOR BEHAVIORAL QUESTIONS:
- Use STAR format (Situation, Task, Action, Result) but keep it tight
- Pull specific details from my resume: team sizes, technologies, metrics
- If no exact match, bridge to closest related experience

FOR TECHNICAL QUESTIONS I LACK EXPERIENCE IN:
- Give a concise explanation showing I understand the concept
- Bridge: "I haven't implemented X directly, but in my work on [related thing], I used similar principles..."

TONE: Confident peer. No hedging like "I think maybe..." - speak with authority."""
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

    async def stream_response(
        self,
        question: str,
        messages: list[dict[str, str]] | None = None,
    ) -> str:
        """Stream a response from Claude.

        Args:
            question: The user's question/prompt.
            messages: Optional conversation history for multi-turn sessions.

        Returns:
            The complete response text for session tracking.
        """
        if not self._ensure_client():
            return ""

        try:
            conversation = messages.copy() if messages else []
            conversation.append({"role": "user", "content": question})

            full_response = ""
            with self._client.messages.stream(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                system=self._build_system_prompt(),
                messages=conversation,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    self.text_chunk.emit(text)

            self.response_complete.emit()
            return full_response

        except Exception as e:
            self.error_occurred.emit(f"Claude error: {e}")
            return ""

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
