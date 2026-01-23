from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass(frozen=True)
class ClaudeConfig:
    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 1024


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
        base_instruction = "You are answering an interview question. Be concise and confident."
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
                system=self._build_system_prompt(),
                messages=[{"role": "user", "content": question}],
            ) as stream:
                for text in stream.text_stream:
                    self.text_chunk.emit(text)

            self.response_complete.emit()

        except Exception as e:
            self.error_occurred.emit(f"Claude error: {e}")
