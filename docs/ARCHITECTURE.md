# Architecture

System architecture documentation.

## Provider System

The application uses a provider-based architecture for LLM interactions. Providers are responsible for streaming responses back to the application via Qt signals.

### Asynchronous Streaming

Providers (such as `ClaudeProvider`) utilize asynchronous clients (`AsyncAnthropic`) to handle streaming responses without blocking the main event loop. This improves latency and responsiveness during long-running generation tasks.

### Error Recovery

A robust error recovery mechanism is implemented in the streaming pipeline:
- **Signal Reconnection**: On streaming errors, the application attempts to reconnect loopback signals to ensure subsequent requests can proceed.
- **Graceful Failure**: Errors are caught and emitted via the `error_occurred` signal, allowing the UI to notify the user while maintaining stable application state.
