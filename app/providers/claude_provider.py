"""Claude AI provider implementation."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from anthropic import Anthropic

from .base import BaseProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaudeConfig:
    """Configuration for Claude API calls."""

    model: str = "claude-sonnet-4-5-20250929"
    max_tokens: int = 768
    temperature: float = 0.7


class ClaudeProvider(BaseProvider):
    """Claude AI streaming provider using Anthropic API.

    Handles streaming responses from Claude models and emits
    Qt signals for each chunk, completion, and errors.
    """

    MODEL_SONNET = "claude-sonnet-4-5-20250929"
    ENV_API_KEY = "ANTHROPIC_API_KEY"

    def __init__(self, config: Optional[ClaudeConfig] = None) -> None:
        """Initialize Claude provider.

        Args:
            config: Optional configuration for model, tokens, temperature.

        Raises:
            ValueError: If ANTHROPIC_API_KEY environment variable is not set.
        """
        super().__init__()
        self._config = config or ClaudeConfig()
        self._api_key = os.getenv(self.ENV_API_KEY, "")
        self._client: Optional[Anthropic] = None

        if not self._api_key:
            logger.error("ANTHROPIC_API_KEY not set in environment")

    def _ensure_client(self) -> bool:
        """Ensure the Anthropic client is initialized.

        Returns:
            True if client is ready, False if API key missing.
        """
        if not self._api_key:
            self.error_occurred.emit("ANTHROPIC_API_KEY not set")
            return False
        if not self._client:
            self._client = Anthropic(api_key=self._api_key)
        return True

    async def stream_response(
        self,
        transcript: str,
        messages: list[dict[str, str]] | None,
        system_prompt: str,
    ) -> str:
        """Stream a response from Claude.

        Args:
            transcript: The current user input/transcript.
            messages: Optional conversation history for multi-turn sessions.
            system_prompt: The system prompt/instruction for the model.

        Returns:
            The complete response text for session tracking.
        """
        if not self._ensure_client():
            return ""

        try:
            conversation = messages.copy() if messages else []
            conversation.append({"role": "user", "content": transcript})

            full_response = ""
            with self._client.messages.stream(
                model=self._config.model,
                max_tokens=self._config.max_tokens,
                temperature=self._config.temperature,
                system=system_prompt,
                messages=conversation,
            ) as stream:
                for text in stream.text_stream:
                    full_response += text
                    self.text_chunk.emit(text)

            self.response_complete.emit()
            return full_response

        except Exception as e:
            error_msg = f"Claude error: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return ""
