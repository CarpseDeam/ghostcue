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

## Interview Recovery Features

To improve reliability during live sessions, the application implements several recovery mechanisms:

- **Manual Control (F9)**: Automatic silence detection is disabled to give the user full control over recording starts and stops, preventing premature cut-offs.
- **Transcript Tracking**: The last captured transcript is stored to allow for immediate retries.
- **Manual Retry (F10)**: Users can re-trigger the generation process for the last transcript if the response was interrupted or unsatisfactory.
- **Manual Cancellation (Escape)**: Ongoing response generation can be cancelled immediately, returning the UI to a ready state.
- **Visual Context**: The overlay displays the "heard" transcript above the AI response, providing clear context for the generated output.

## User Interface & Usability

The `StealthOverlay` is designed for minimal intrusion while providing essential status information:

- **Interactive Hints**: A subtle footer provides immediate guidance on hotkeys: `F9 Record | F10 Retry | Esc Cancel | [C] Copy`.
- **State Feedback**: The UI uses specific labels (e.g., "Listening...", "Processing...", "Thinking...") to keep the user informed of the background worker's status.
- **Recovery Awareness**: On cancellation, the overlay explicitly prompts the user with the retry hotkey (F10), reducing friction during high-pressure sessions.
