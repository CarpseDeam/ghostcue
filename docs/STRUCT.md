# widget-helper

**Language:** python
**Stack:** httpx

## Changelog

_No changes recorded yet._

## Structure

- `app/` - Application code
- `docs/` - Documentation
- `tests/` - Tests

## Components

| Name | Type | Location | Summary |
|------|------|----------|---------|
| Config | dataclass | `config.py` | dataclass |
| PayloadType | class | `contracts.py` | class extending Enum |
| ClipboardPayload | dataclass | `contracts.py` | dataclass |
| AnalysisResult | dataclass | `contracts.py` | dataclass |
| AudioPayload | dataclass | `contracts.py` | dataclass |
| hide_console | function | `main.py` | function |
| main | function | `main.py` | function |
| Analyzer | class | `app\analyzer.py` | class |
| AudioCommand | class | `app\audio_worker.py` | class extending Enum |
| AudioMessage | dataclass | `app\audio_worker.py` | dataclass |
| AudioResult | dataclass | `app\audio_worker.py` | dataclass |
| AudioWorker | class | `app\audio_worker.py` | class |
| worker_main | function | `app\audio_worker.py` | function |
| ClaudeConfig | dataclass | `app\claude_client.py` | dataclass |
| ClaudeStreamingClient | class | `app\claude_client.py` | class extending QObject |
| ClipboardMonitor | class | `app\clipboard.py` | class |
| DeepgramConfig | dataclass | `app\deepgram_client.py` | dataclass |
| DeepgramStreamingClient | class | `app\deepgram_client.py` | class extending QObject |
| LoopbackConfig | dataclass | `app\loopback_client.py` | dataclass |
| LoopbackStreamingClient | class | `app\loopback_client.py` | class extending QObject |
| WorkerConfig | dataclass | `app\loopback_worker.py` | dataclass |
| run_capture_loop | function | `app\loopback_worker.py` | function |
| OCRResult | dataclass | `app\ocr.py` | dataclass |
| WindowsOCR | class | `app\ocr.py` | class |
| StealthOverlay | class | `app\overlay.py` | class extending QWidget |
| AudioRecorder | class | `app\recorder.py` | class |
| SessionManager | class | `app\session_manager.py` | class |
| StealthCapable | interface | `app\stealth.py` | interface extending Protocol |
| make_stealth | function | `app\stealth.py` | function |
| Transcriber | class | `app\transcriber.py` | class |
| SignalBridge | class | `app\tray.py` | class extending QObject |
| FloatingToolbar | class | `app\tray.py` | class extending QWidget |
| TrayApp | class | `app\tray.py` | class |
| HumanTyper | class | `app\typer.py` | class |
| BaseProvider | class | `app\providers\base.py` | class extending QObject |
| ClaudeConfig | dataclass | `app\providers\claude_provider.py` | dataclass |
| ClaudeProvider | class | `app\providers\claude_provider.py` | class extending BaseProvider |
| GeminiProvider | class | `app\providers\gemini_provider.py` | class extending BaseProvider |
| list_all_audio_devices | function | `tests\test_audio_routing.py` | function |
| test_device_capture | test | `tests\test_audio_routing.py` | test |
| speak_test | function | `tests\test_audio_routing.py` | function |
| find_active_device | function | `tests\test_audio_routing.py` | function |
| StreamingConfig | dataclass | `tests\test_claude_streaming.py` | dataclass |
| get_question | function | `tests\test_claude_streaming.py` | function |
| stream_response | function | `tests\test_claude_streaming.py` | function |
| main | function | `tests\test_claude_streaming.py` | function |
| StreamingConfig | dataclass | `tests\test_deepgram_streaming.py` | dataclass |
| DeepgramStreamer | class | `tests\test_deepgram_streaming.py` | class |
| main | function | `tests\test_deepgram_streaming.py` | function |
| TestResult | dataclass | `tests\test_full_pipeline.py` | dataclass |
| speak_question | function | `tests\test_full_pipeline.py` | function |
| run_pipeline_test | function | `tests\test_full_pipeline.py` | async function |
| main | function | `tests\test_full_pipeline.py` | async function |
| main | function | `tests\test_loopback_client.py` | async function |
| get_loopback_microphone | function | `tests\test_wasapi_loopback.py` | function |
| calculate_rms | function | `tests\test_wasapi_loopback.py` | function |
| convert_to_mono | function | `tests\test_wasapi_loopback.py` | function |
| resample_audio | function | `tests\test_wasapi_loopback.py` | function |
| save_wav | function | `tests\test_wasapi_loopback.py` | function |
| record_loopback_audio | function | `tests\test_wasapi_loopback.py` | function |
| main | function | `tests\test_wasapi_loopback.py` | function |

## Patterns

- **errors**: Custom exception classes
- **auth**: API Keys
- **di**: Container-based DI
- **tests**: Pytest function-based tests
- **async**: Async/await (29+ async functions)

## Stats

- files: 33
- dirs: 5
- lines: 4010
