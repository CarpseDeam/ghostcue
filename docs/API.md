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

**Features:**
- **Markdown Rendering**: Supports code blocks and inline formatting.
- **Cheat Sheet**: Displays a persistent footer with hotkey reminders: `F8 Text | F9 Record | F10 Retry | Esc Cancel`.

**Methods:**
- `show_transcript(text: str) -> None`: Displays the captured transcript text or clipboard input above the response area.
- `clear_and_show() -> None`: Clears previous content and ensures the overlay is visible.
- `show_response(text: str) -> None`: Displays the final response or status message.
- `show_error(error: str) -> None`: Displays an error message in the overlay.

## Hotkeys

### Global Hotkeys
- **F8**: Process clipboard text as input.
- **F9**: Start/Stop recording (Toggle) - **Manual control only** (silence detection disabled).
- **F10**: Retry last transcript or clipboard input.
- **Escape**: Cancel current response streaming.

### Overlay Controls
- **F8**: Process clipboard text.
- **F9**: Start/Stop recording.
- **F10**: Retry last input.
- **Escape**: Cancel response or hide overlay.
- **Left Mouse Drag**: Move overlay.
- **Bottom-Right Corner**: Resize overlay.
