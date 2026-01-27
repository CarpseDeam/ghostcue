# widget-helper

**Language:** python

## Structure

- `app/` - Core application logic and providers
  - `providers/` - LLM backend implementations (Claude, Gemini)
- `docs/` - Documentation files
- `tests/` - Unit and integration tests

## Key Files

- `main.py` - Application entry point and tray initialization
- `config.py` - Configuration management using environment variables
- `contracts.py` - Data classes and shared protocols
- `requirements.txt` - Project dependencies

## Module Details

### `app/`
- `analyzer.py`: Text analysis logic
- `audio_worker.py`: Background worker for audio processing
- `claude_client.py`: Streaming client for Claude
- `clipboard.py`: Clipboard monitoring utility
- `deepgram_client.py`: Deepgram transcription client
- `loopback_client.py`: System audio capture client
- `loopback_worker.py`: Background worker for audio streaming
- `ocr.py`: Windows OCR integration
- `overlay.py`: HUD/Overlay UI component
- `recorder.py`: Audio recording management
- `session_manager.py`: Application session state
- `stealth.py`: Anti-detection and window management
- `transcriber.py`: Transcription orchestration
- `tray.py`: System tray icon and toolbar
- `typer.py`: Human-like typing simulation

### `app/providers/`
- `base.py`: Abstract base class for AI providers
- `claude_provider.py`: Async implementation for Anthropic Claude (AsyncAnthropic)
- `gemini_provider.py`: Implementation for Google Gemini

## Entry Points

- **Main Application**: `python main.py`
- **Tests**: `pytest tests/`

## Stats (Approximate)

- Files: ~20 core source files
- Directories: 5 major directories
- Tests: 10+ test suites