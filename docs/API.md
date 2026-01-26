# API Reference

## Providers

### BaseProvider (Abstract)

Base class for all AI streaming providers. Inherits from `QObject`.

**Signals:**
- `text_chunk(str)`: Emitted when a new piece of text is received.
- `response_complete()`: Emitted when the response is finished.
- `error_occurred(str)`: Emitted when an error happens.

**Methods:**
- `async stream_response(transcript: str, messages: list[dict], system_prompt: str) -> str`: Streams response from the provider.

### ClaudeProvider

Implementation of `BaseProvider` using Anthropic's Claude.

**Implementation Details:**
- Uses `AsyncAnthropic` for non-blocking streaming.
- **Error Handling**: Implements automatic loopback signal reconnection on streaming errors to ensure system stability.
- **Configuration**: Managed via `ClaudeConfig` (model, max_tokens, temperature).

## UI Components

### StealthOverlay

The transparent overlay used to display transcriptions and AI responses.

**Methods:**
- `show_transcript(text: str) -> None`: Displays the captured transcript text above the response area.
- `clear_and_show() -> None`: Clears previous content and ensures the overlay is visible.
- `show_response(text: str) -> None`: Displays the final response or status message.
- `show_error(error: str) -> None`: Displays an error message in the overlay.

## Hotkeys

- **F9**: Start/Stop recording (Toggle).
- **F10**: Retry last transcript.
- **Escape**: Cancel current response streaming.
