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
