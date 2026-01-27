# GhostCue

**Real-time conversational AI assistant with audio capture and context persistence.**

Listens to system audio, transcribes in real-time, provides AI-powered responses in a minimal stealth overlay.

## What It Does

- Captures system audio (WASAPI loopback) and transcribes speech in real-time via Deepgram
- Sends transcripts to AI (Claude or Gemini) along with your custom context
- Displays responses in a minimal, always-on-top overlay designed to stay out of the way
- Maintains conversation history for natural multi-turn exchanges
- Supports screenshot OCR for visual content analysis

## Use Cases

- **Accessibility** — Processing aid for neurodivergent individuals during live conversations
- **Language support** — Real-time assistance for ESL speakers in meetings
- **Learning & tutoring** — Ask questions about what's being explained as you hear it
- **Technical support** — Instant reference to complex knowledge bases during calls
- **Presentations** — Live Q&A assistance with your prepared materials
- **Meeting support** — Context-aware notes and responses during discussions

## Features

| Hotkey | Action |
|--------|--------|
| **F9** | Toggle audio recording |
| **F8** | Send clipboard text |
| **F10** | Retry last response |
| **Esc** | Cancel current request |

**Additional capabilities:**
- Screenshot queue — Capture multiple images, send together with OCR
- Session persistence — Full conversation history maintained across interactions
- Multiple AI providers — Claude, Gemini Pro, Gemini Flash (switchable via tray menu)
- Stealth overlay — Window excluded from screen capture and recordings

## Requirements

- Windows 10/11
- Python 3.11+
- API keys:
  - [Deepgram](https://deepgram.com/) — Speech-to-text
  - [Anthropic](https://anthropic.com/) (Claude) and/or [Google](https://ai.google.dev/) (Gemini)

## Installation

```bash
git clone https://github.com/yourusername/ghostcue.git
cd ghostcue

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
DEEPGRAM_API_KEY=your_deepgram_key
ANTHROPIC_API_KEY=your_anthropic_key
GEMINI_API_KEY=your_google_key
```

## Configuration

| File | Purpose |
|------|---------|
| `context.txt` | Your custom context/knowledge base the AI references |
| `config.py` | Overlay appearance, timeouts, hotkey behavior |

## Usage

1. Add your context or reference material to `context.txt`
2. Run `python main.py`
3. App appears in the system tray
4. Press **F9** to start listening, **F9** again to stop and get a response
5. Response appears in the overlay

The floating toolbar provides quick access to screenshot capture, session reset, and provider switching.

## Tech Stack

- **GUI**: PyQt6 with qasync for async event loop integration
- **Audio**: WASAPI loopback via soundcard, scipy for resampling
- **Transcription**: Deepgram streaming (WebSocket, nova-3 model)
- **AI**: Anthropic Claude / Google Gemini with streaming responses
- **OCR**: Windows native OCR via winocr
- **Hotkeys**: pynput for global keyboard shortcuts

## Project Structure

```
ghostcue/
├── main.py              # Entry point
├── config.py            # Configuration
├── context.txt          # Your custom AI context
├── app/
│   ├── tray.py          # System tray app and toolbar
│   ├── overlay.py       # Response display overlay
│   ├── recorder.py      # Audio capture
│   ├── deepgram_client.py   # Real-time transcription
│   ├── session_manager.py   # Conversation history
│   └── providers/       # AI provider implementations
│       ├── claude_provider.py
│       └── gemini_provider.py
└── docs/                # Architecture and API docs
```

## License

MIT
