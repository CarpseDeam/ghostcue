"""Abstract base class defining the provider interface."""

from __future__ import annotations

from abc import abstractmethod

from PyQt6.QtCore import QObject, pyqtSignal


class BaseProvider(QObject):
    """Abstract base class for AI streaming providers.

    All providers must emit signals for streaming chunks, completion,
    and errors. This enables a unified interface for the UI layer
    regardless of which AI backend is used.

    Signals:
        text_chunk: Emitted for each streaming text chunk.
        response_complete: Emitted when streaming finishes successfully.
        error_occurred: Emitted when an error occurs during streaming.
    """

    text_chunk = pyqtSignal(str)
    response_complete = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self) -> None:
        """Initialize the base provider."""
        super().__init__()

    @abstractmethod
    async def stream_response(
        self,
        transcript: str,
        messages: list[dict[str, str]] | None,
        system_prompt: str,
    ) -> str:
        """Stream a response from the AI provider.

        Args:
            transcript: The current user input/transcript.
            messages: Optional conversation history for multi-turn sessions.
                Each dict has 'role' ('user' or 'assistant') and 'content'.
            system_prompt: The system prompt/instruction for the model.

        Returns:
            The complete response text for session tracking.

        Raises:
            NotImplementedError: Subclasses must implement this method.
        """
        raise NotImplementedError
