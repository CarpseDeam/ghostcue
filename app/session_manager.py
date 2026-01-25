"""Session manager for persistent conversation history with Claude API."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Literal

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages conversation history for persistent session mode.

    Handles message storage and retrieval for multi-turn conversations
    with the Claude API. Does not interact with Qt or UI components.
    """

    def __init__(self) -> None:
        """Initialize session manager with empty state."""
        self._messages: list[dict[str, str]] = []
        self._persistent_mode: bool = False

    @property
    def persistent_mode(self) -> bool:
        """Get current persistent mode state."""
        return self._persistent_mode

    @persistent_mode.setter
    def persistent_mode(self, value: bool) -> None:
        """Set persistent mode state.

        Args:
            value: True to enable persistent sessions, False to disable.
        """
        if self._persistent_mode != value:
            self._persistent_mode = value
            logger.debug("Persistent mode toggled: %s", value)

    def add_user_message(self, content: str) -> None:
        """Add a user message to the conversation history.

        Args:
            content: The user's message content.
        """
        if not content.strip():
            return
        self._messages.append({"role": "user", "content": content})
        logger.debug("Added user message, total messages: %d", len(self._messages))

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to the conversation history.

        Args:
            content: The assistant's response content.
        """
        if not content.strip():
            return
        self._messages.append({"role": "assistant", "content": content})
        logger.debug("Added assistant message, total messages: %d", len(self._messages))

    def get_messages(self) -> list[dict[str, str]]:
        """Get a copy of the conversation history.

        Returns:
            Copy of messages list to prevent external modification.
        """
        return self._messages.copy()

    def clear(self) -> None:
        """Clear all conversation history."""
        count = len(self._messages)
        self._messages.clear()
        logger.debug("Session cleared, removed %d messages", count)

    def is_empty(self) -> bool:
        """Check if conversation history is empty.

        Returns:
            True if no messages stored, False otherwise.
        """
        return len(self._messages) == 0
