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

## Unified Input Flow

All input methods—Solve, Analyze, Audio (F9), and Text (F8)—are routed through a unified `_stream_and_track_response` pipeline. This ensures:
- **Consistent Session History**: Follow-up questions via any method maintain context from previous interactions.
- **Batch Processing**: Multiple screenshots can be queued via the Snip tool. The Solve and Analyze actions process all queued items simultaneously, performing OCR on each and concatenating the results for the LLM.
- **OCR Integration**: Image-based inputs (screenshots) automatically undergo OCR before being processed by the unified flow.
- **Unified Retries**: The F10 hotkey retries the last input regardless of the source (audio or text).

## Assistant Recovery Features

To improve reliability during live sessions, the application implements several recovery mechanisms:

- **Manual Control (F9)**: Automatic silence detection is disabled to give the user full control over recording starts and stops, preventing premature cut-offs.
- **Text Input (F8)**: Users can grab text from the system clipboard and send it as a prompt, allowing for quick follow-ups on written content while maintaining session history.
- **Session Reset (R)**: A dedicated reset button on the toolbar allows users to immediately clear session history and start fresh.
- **Transcript Tracking**: The last captured transcript (or clipboard text) is stored to allow for immediate retries.
- **Manual Retry (F10)**: Users can re-trigger the generation process for the last transcript if the response was interrupted or unsatisfactory.
- **Manual Cancellation (Escape)**: Ongoing response generation can be cancelled immediately, returning the UI to a ready state.
- **Visual Context**: The overlay displays the "heard" transcript or source text above the AI response, providing clear context for the generated output.

## Conversational Assistant Persona

The application is tuned for real-time conversational assistance where responses are intended to be clear, direct, and helpful:

- **Verbal Optimization**: Prompts are engineered to focus on conversational explanations (75-100 words) that are easy to process and understand when heard.
- **First-Person Delivery**: Responses are generated in the first person ("I built...", "In my experience...") to provide natural-sounding assistance.
- **Context-Aware Responses**: The system differentiates between input types to provide optimized answers:
    - **Technical Concepts**: Direct explanations without unnecessary filler.
    - **Behavioral/Contextual**: Uses structured formats (like STAR) when referencing personal experience or history from the knowledge base.
    - **System Design/Problem Solving**: Structured walkthroughs (requirements → components → trade-offs).
    - **Knowledge Retrieval**: Honest evaluation of available information with bridging to related concepts if needed.
- **Logic Placement**: Prompt logic is primarily maintained in `context.txt` for easier iteration, with `app/tray.py` providing the core verbal constraints.

## User Interface & Usability

The `StealthOverlay` is designed for minimal intrusion while providing essential status information:

- **Interactive Hints**: A subtle footer provides immediate guidance on hotkeys: `F8 Text | F9 Record | F10 Retry | Esc Cancel`.
- **Reliable Clipboard**: Uses `pyperclip` as a cross-platform backend to ensure copied text persists in the system clipboard even after the overlay state changes.
- **State Feedback**: The UI uses specific labels (e.g., "Listening...", "Processing...", "Thinking...") to keep the user informed of the background worker's status.
- **Recovery Awareness**: On cancellation, the overlay explicitly prompts the user with the retry hotkey (F10), reducing friction during high-pressure sessions.
