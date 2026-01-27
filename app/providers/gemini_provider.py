"""Gemini AI provider implementation using google-genai."""

from __future__ import annotations

import logging
import os
from typing import Optional

from google import genai
from google.genai import types

from .base import BaseProvider

logger = logging.getLogger(__name__)


class GeminiProvider(BaseProvider):
    """Gemini AI streaming provider using Google GenAI API.

    Handles streaming responses from Gemini models and emits
    Qt signals for each chunk, completion, and errors.
    """

    MODEL_PRO = "gemini-3-pro-preview"
    MODEL_FLASH = "gemini-3-flash-preview"
    ENV_API_KEY = "GEMINI_API_KEY"

    def __init__(self, model: str = MODEL_FLASH) -> None:
        """Initialize Gemini provider.

        Args:
            model: The Gemini model to use (default: gemini-3-flash-preview).

        Raises:
            ValueError: If GEMINI_API_KEY environment variable is not set.
        """
        super().__init__()
        self._model = model
        self._api_key = os.getenv(self.ENV_API_KEY, "")
        self._client: Optional[genai.Client] = None

        if not self._api_key:
            logger.error("GEMINI_API_KEY not set in environment")

    def _ensure_client(self) -> bool:
        """Ensure the Gemini client is initialized.

        Returns:
            True if client is ready, False if API key missing.
        """
        if not self._api_key:
            self.error_occurred.emit("GEMINI_API_KEY not set")
            return False
        if not self._client:
            self._client = genai.Client()
        return True

    def _convert_messages_to_contents(
        self,
        transcript: str,
        messages: list[dict[str, str]] | None,
    ) -> list[types.Content]:
        """Convert message history to Gemini Content format.

        Args:
            transcript: The current user input.
            messages: Optional conversation history.

        Returns:
            List of Content objects for Gemini API.
        """
        contents: list[types.Content] = []

        if messages:
            for msg in messages:
                role = "user" if msg["role"] == "user" else "model"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(msg["content"])],
                    )
                )

        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(transcript)],
            )
        )

        return contents

    async def stream_response(
        self,
        transcript: str,
        messages: list[dict[str, str]] | None,
        system_prompt: str,
    ) -> str:
        """Stream a response from Gemini.

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
            contents = self._convert_messages_to_contents(transcript, messages)
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=2048,
            )

            full_response = ""
            async for chunk in await self._client.aio.models.generate_content_stream(
                model=self._model,
                contents=contents,
                config=config,
            ):
                if chunk.text:
                    full_response += chunk.text
                    self.text_chunk.emit(chunk.text)

            self.response_complete.emit()
            return full_response

        except Exception as e:
            error_msg = f"Gemini error: {e}"
            logger.error(error_msg)
            self.error_occurred.emit(error_msg)
            return ""
