from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import threading
from typing import Optional, Callable

from pynput import keyboard as pynput_keyboard

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QActionGroup

from config import Config
from contracts import ClipboardPayload, PayloadType
from app.clipboard import ClipboardMonitor
from app.analyzer import Analyzer
from app.typer import HumanTyper
from app.stealth import make_stealth
from app.overlay import StealthOverlay
from app.deepgram_client import DeepgramStreamingClient
from app.claude_client import ClaudeStreamingClient
from app.loopback_client import LoopbackStreamingClient
from app.session_manager import SessionManager
from app.providers import ClaudeProvider, GeminiProvider
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    clipboard_changed = pyqtSignal(object)
    analysis_complete = pyqtSignal(str)
    audio_complete = pyqtSignal(str)
    streaming_error = pyqtSignal(str)
    hotkey_pressed = pyqtSignal()


class FloatingToolbar(QWidget):
    def __init__(
        self,
        on_audio_click: Optional[Callable[[], None]] = None,
        on_solve_click: Optional[Callable[[], None]] = None,
        on_explain_click: Optional[Callable[[], None]] = None,
        on_git_click: Optional[Callable[[], None]] = None,
        config: Config = None
    ) -> None:
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._on_audio_callback = on_audio_click
        self._on_solve_callback = on_solve_click
        self._on_explain_callback = on_explain_click
        self._on_git_callback = on_git_click
        self._config = config or Config()
        self._is_recording = False
        self._clipboard_ready = False
        self._image_ready = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._container = QWidget()
        self._container.setStyleSheet("background-color: rgba(45, 45, 45, 230); border-radius: 6px;")

        layout = QHBoxLayout(self._container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        btn_size = self._config.button_size

        self._snip_btn = QPushButton("\u25f2")
        self._snip_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #a569c6;
            }
        """)
        self._snip_btn.setFixedSize(btn_size, btn_size)
        self._snip_btn.clicked.connect(self._on_snip_click)
        layout.addWidget(self._snip_btn)

        self._audio_btn = QPushButton("\u25cf")
        self._audio_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f75c4c;
            }
        """)
        self._audio_btn.setFixedSize(btn_size, btn_size)
        self._audio_btn.setToolTip("Click to record")
        self._audio_btn.clicked.connect(self._on_audio_click)
        layout.addWidget(self._audio_btn)

        self._solve_btn = QPushButton("S")
        self._solve_btn.setFixedSize(btn_size, btn_size)
        self._solve_btn.setEnabled(False)
        self._solve_btn.clicked.connect(self._on_solve_click)
        self._update_solve_style()
        layout.addWidget(self._solve_btn)

        self._explain_btn = QPushButton("A")
        self._explain_btn.setFixedSize(btn_size, btn_size)
        self._explain_btn.setEnabled(False)
        self._explain_btn.clicked.connect(self._on_explain_click)
        self._update_explain_style()
        layout.addWidget(self._explain_btn)

        self._git_btn = QPushButton("G")
        self._git_btn.setFixedSize(btn_size, btn_size)
        self._git_btn.setEnabled(False)
        self._git_btn.setToolTip("Generate commit message from screenshot")
        self._git_btn.clicked.connect(self._on_git_click)
        self._update_git_style()
        layout.addWidget(self._git_btn)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

    def _on_snip_click(self) -> None:
        subprocess.run(['explorer', 'ms-screenclip:'], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def _on_audio_click(self) -> None:
        if self._on_audio_callback:
            self._on_audio_callback()

    def _on_solve_click(self) -> None:
        if self._on_solve_callback and self._clipboard_ready:
            self._on_solve_callback()

    def _on_explain_click(self) -> None:
        if self._on_explain_callback and self._clipboard_ready:
            self._on_explain_callback()

    def _on_git_click(self) -> None:
        if self._on_git_callback and self._image_ready:
            self._on_git_callback()

    def _update_solve_style(self) -> None:
        if self._solve_btn.isEnabled():
            self._solve_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2ecc71;
                }
            """)
        else:
            self._solve_btn.setStyleSheet("""
                QPushButton {
                    background-color: #555555;
                    color: #888888;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }
            """)

    def _update_explain_style(self) -> None:
        if self._explain_btn.isEnabled():
            self._explain_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #5dade2;
                }
            """)
        else:
            self._explain_btn.setStyleSheet("""
                QPushButton {
                    background-color: #555555;
                    color: #888888;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }
            """)

    def _update_git_style(self) -> None:
        if self._git_btn.isEnabled():
            self._git_btn.setStyleSheet("""
                QPushButton {
                    background-color: #f39c12;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #f5b041;
                }
            """)
        else:
            self._git_btn.setStyleSheet("""
                QPushButton {
                    background-color: #555555;
                    color: #888888;
                    border: none;
                    border-radius: 6px;
                    font-size: 16px;
                    font-weight: bold;
                }
            """)

    def set_clipboard_ready(self, ready: bool) -> None:
        self._clipboard_ready = ready
        self._solve_btn.setEnabled(ready)
        self._explain_btn.setEnabled(ready)
        self._update_solve_style()
        self._update_explain_style()

    def set_image_ready(self, ready: bool) -> None:
        self._image_ready = ready
        self._git_btn.setEnabled(ready)
        self._update_git_style()

    def set_processing(self, processing: bool) -> None:
        self._solve_btn.setEnabled(not processing and self._clipboard_ready)
        self._explain_btn.setEnabled(not processing and self._clipboard_ready)
        if processing:
            self._solve_btn.setText("...")
            self._explain_btn.setText("...")
        else:
            self._solve_btn.setText("S")
            self._explain_btn.setText("A")
        self._update_solve_style()
        self._update_explain_style()

    def set_recording_state(self, is_recording: bool) -> None:
        self._is_recording = is_recording
        if is_recording:
            self._audio_btn.setText("■")
            self._audio_btn.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #2ecc71;
                }
            """)
            self._audio_btn.setToolTip("Listening... Click to stop")
        else:
            self._audio_btn.setText("●")
            self._audio_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 6px;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #f75c4c;
                }
            """)
            self._audio_btn.setToolTip("Click to record")

    def set_audio_processing(self, processing: bool) -> None:
        self._audio_btn.setEnabled(not processing)
        if processing:
            self._audio_btn.setText("...")
        else:
            self.set_recording_state(False)

    def position_near_overlay(self, overlay_x: int, overlay_y: int, overlay_width: int) -> None:
        self.adjustSize()
        x = overlay_x + overlay_width + 10
        y = overlay_y
        self.move(x, y)

    def show_in_corner(self) -> None:
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.left() + 20
        y = screen.bottom() - self.height() - 20
        self.move(x, y)
        self.show()
        make_stealth(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None


class TrayApp:
    PROVIDER_CLAUDE = "claude"
    PROVIDER_GEMINI_PRO = "gemini_pro"
    PROVIDER_GEMINI_FLASH = "gemini_flash"

    CONTEXT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "context.txt")

    def __init__(self, config: Config, loop: asyncio.AbstractEventLoop) -> None:
        self._config = config
        self._loop = loop
        self._app = QApplication.instance()

        self._signals = SignalBridge()
        self._signals.clipboard_changed.connect(self._on_clipboard_signal)
        self._signals.analysis_complete.connect(self._on_analysis_complete)
        self._signals.audio_complete.connect(self._on_audio_complete)
        self._signals.streaming_error.connect(self._on_streaming_error)
        self._signals.hotkey_pressed.connect(self._on_audio_button_click)

        self._analyzer = Analyzer()
        self._typer = HumanTyper()
        self._session_manager = SessionManager()
        self._is_recording = False
        self._is_responding = False
        self._f9_pressed: bool = False
        self._pending_payload: Optional[ClipboardPayload] = None
        self._streaming_task: Optional[asyncio.Task] = None
        self._hotkey_listener: Optional[pynput_keyboard.Listener] = None
        self._pending_transcript: str = ""
        self._last_transcript: str = ""
        self._system_prompt = self._build_system_prompt()

        self._overlay = StealthOverlay(config)

        self._deepgram = DeepgramStreamingClient()
        self._claude = ClaudeStreamingClient()
        self._loopback = LoopbackStreamingClient()
        self._loopback.set_silence_threshold(
            self._config.silence_threshold_ms,
            self._config.question_silence_threshold_ms
        )

        self._claude_provider = ClaudeProvider()
        self._gemini_pro_provider = GeminiProvider(model=GeminiProvider.MODEL_PRO)
        self._gemini_flash_provider = GeminiProvider(model=GeminiProvider.MODEL_FLASH)
        self._active_provider: BaseProvider = self._claude_provider
        self._active_provider_name = self.PROVIDER_CLAUDE

        self._connect_streaming_signals()
        self._connect_loopback_signals()
        self._connect_provider_signals()

        self._setup_tray()
        self._setup_toolbar()
        self._setup_clipboard_monitor()
        self._setup_hotkey()

        asyncio.run_coroutine_threadsafe(self._warm_up_loopback(), self._loop)

    async def _warm_up_loopback(self) -> None:
        success = await self._loopback.warm_up()
        if success:
            print("[DEBUG] Loopback pre-warmed successfully")
        else:
            print("[DEBUG] Loopback warm-up failed, will use cold start")

    def _connect_streaming_signals(self) -> None:
        self._deepgram.interim_transcript.connect(self._overlay.interim_transcript.emit)
        self._deepgram.final_transcript.connect(self._on_final_transcript)
        self._deepgram.error_occurred.connect(self._on_streaming_error)

        self._claude.text_chunk.connect(self._overlay.text_chunk_received.emit)
        self._claude.response_complete.connect(self._on_response_complete)
        self._claude.error_occurred.connect(self._on_streaming_error)

    def _connect_loopback_signals(self) -> None:
        self._loopback.interim_interviewer.connect(self._on_interim_update)
        self._loopback.final_interviewer.connect(self._on_interim_update)
        self._loopback.error_occurred.connect(self._on_streaming_error)
        # silence_detected disabled - full manual control with F9

    def _disconnect_loopback_signals(self) -> None:
        try:
            self._loopback.interim_interviewer.disconnect(self._on_interim_update)
        except TypeError:
            pass
        try:
            self._loopback.final_interviewer.disconnect(self._on_interim_update)
        except TypeError:
            pass

    def _reconnect_loopback_signals(self) -> None:
        try:
            self._loopback.interim_interviewer.disconnect(self._on_interim_update)
        except TypeError:
            pass
        try:
            self._loopback.final_interviewer.disconnect(self._on_interim_update)
        except TypeError:
            pass
        self._loopback.interim_interviewer.connect(self._on_interim_update)
        self._loopback.final_interviewer.connect(self._on_interim_update)

    def _connect_provider_signals(self) -> None:
        """Connect all provider signals to overlay handlers."""
        for provider in (
            self._claude_provider,
            self._gemini_pro_provider,
            self._gemini_flash_provider,
        ):
            provider.text_chunk.connect(self._overlay.text_chunk_received.emit)
            provider.response_complete.connect(self._on_response_complete)
            provider.error_occurred.connect(self._on_streaming_error)

    def _load_context(self) -> str:
        """Load context from context.txt file."""
        try:
            with open(self.CONTEXT_PATH, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return ""

    def _build_system_prompt(self) -> str:
        """Build the system prompt with context and base instructions."""
        context = self._load_context()
        base_instruction = """You are ME in a technical interview. You have access to my resume above. Speak as if YOU lived these experiences.

CRITICAL: THIS IS A VERBAL INTERVIEW - I will be SPEAKING your response out loud.
- NO CODE BLOCKS. Never. I cannot recite code verbally.
- Explain concepts conversationally, like you're talking to the interviewer
- For system design: describe components, data flow, trade-offs in plain English
- A one-liner pseudocode reference is okay ("I'd use a dictionary mapping user IDs to timestamps")
- Keep responses under 30 seconds of speaking time (~75-100 words)

RESPONSE RULES:
- First-person ONLY. Say "I built..." not "You could say..."
- Lead with the answer. No preamble like "Great question!"
- Be concise. Interviewers can ask follow-ups.

FOR BEHAVIORAL QUESTIONS:
- Use STAR format (Situation, Task, Action, Result) but keep it tight
- Pull specific details from my resume: team sizes, technologies, metrics
- If no exact match, bridge to closest related experience

FOR TECHNICAL QUESTIONS I LACK EXPERIENCE IN:
- Give a concise explanation showing I understand the concept
- Bridge: "I haven't implemented X directly, but in my work on [related thing], I used similar principles..."

TONE: Confident peer. No hedging like "I think maybe..." - speak with authority."""
        if context:
            return f"{context}\n\n---\n\n{base_instruction}"
        return base_instruction

    def _create_icon(self) -> QIcon:
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor(0, 0, 0, 0))
        painter = QPainter(pixmap)
        painter.setBrush(QColor("#5a5a5a"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 2, 28, 28, 4, 4)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(6, 8, 20, 3)
        painter.drawRect(6, 14, 20, 3)
        painter.drawRect(6, 20, 14, 3)
        painter.end()
        return QIcon(pixmap)

    def _setup_tray(self) -> None:
        self._tray = QSystemTrayIcon(self._create_icon(), self._app)
        self._tray.setToolTip("Clipboard Helper")

        menu = QMenu()

        self._persistent_action = QAction("Persistent Session", checkable=True)
        self._persistent_action.setChecked(self._session_manager.persistent_mode)
        self._persistent_action.triggered.connect(self._on_toggle_persistent_mode)
        menu.addAction(self._persistent_action)

        self._clear_session_action = QAction("Clear Session")
        self._clear_session_action.triggered.connect(self._on_clear_session)
        self._clear_session_action.setEnabled(False)
        menu.addAction(self._clear_session_action)

        menu.addSeparator()

        provider_menu = menu.addMenu("AI Provider")
        self._provider_action_group = QActionGroup(provider_menu)
        self._provider_action_group.setExclusive(True)

        self._claude_action = QAction("Claude", checkable=True)
        self._claude_action.setChecked(True)
        self._claude_action.triggered.connect(lambda: self._on_provider_change(self.PROVIDER_CLAUDE))
        self._provider_action_group.addAction(self._claude_action)
        provider_menu.addAction(self._claude_action)

        self._gemini_pro_action = QAction("Gemini Pro", checkable=True)
        self._gemini_pro_action.triggered.connect(lambda: self._on_provider_change(self.PROVIDER_GEMINI_PRO))
        self._provider_action_group.addAction(self._gemini_pro_action)
        provider_menu.addAction(self._gemini_pro_action)

        self._gemini_flash_action = QAction("Gemini Flash", checkable=True)
        self._gemini_flash_action.triggered.connect(lambda: self._on_provider_change(self.PROVIDER_GEMINI_FLASH))
        self._provider_action_group.addAction(self._gemini_flash_action)
        provider_menu.addAction(self._gemini_flash_action)

        menu.addSeparator()

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        self._tray.setContextMenu(menu)
        self._tray.show()

    def _setup_toolbar(self) -> None:
        self._toolbar = FloatingToolbar(
            on_audio_click=self._on_audio_button_click,
            on_solve_click=self._on_solve_click,
            on_explain_click=self._on_explain_click,
            on_git_click=self._on_git_click,
            config=self._config
        )
        self._toolbar.show_in_corner()

    def _setup_clipboard_monitor(self) -> None:
        self._monitor = ClipboardMonitor(self._on_clipboard_change)
        self._monitor.start()

    def _setup_hotkey(self) -> None:
        def on_press(key: pynput_keyboard.Key | pynput_keyboard.KeyCode | None) -> None:
            try:
                if key == pynput_keyboard.Key.f9:
                    if not self._f9_pressed:
                        self._f9_pressed = True
                        print("[DEBUG] F9 hotkey pressed!")
                        self._signals.hotkey_pressed.emit()
                    else:
                        print("[DEBUG] F9 ignored (key repeat)")
                elif key == pynput_keyboard.Key.f10:
                    self._on_retry_hotkey()
                elif key == pynput_keyboard.Key.esc:
                    self._on_cancel_response()
            except Exception as e:
                print(f"[DEBUG] Hotkey callback error: {e}")

        def on_release(key: pynput_keyboard.Key | pynput_keyboard.KeyCode | None) -> None:
            try:
                if key == pynput_keyboard.Key.f9:
                    self._f9_pressed = False
            except Exception:
                pass

        try:
            self._hotkey_listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
            self._hotkey_listener.start()
            print("[DEBUG] F9/F10/Escape hotkeys registered via pynput")
        except Exception as e:
            print(f"[DEBUG] Failed to register hotkeys: {e}")

    def _on_clipboard_change(self, payload: ClipboardPayload) -> None:
        self._signals.clipboard_changed.emit(payload)

    def _on_clipboard_signal(self, payload: ClipboardPayload) -> None:
        self._pending_payload = payload
        self._toolbar.set_clipboard_ready(True)
        self._toolbar.set_image_ready(payload.payload_type == PayloadType.IMAGE)
        self._toolbar.set_processing(False)

    def _on_solve_click(self) -> None:
        if not self._pending_payload:
            return
        self._toolbar.set_processing(True)
        instruction = """DO NOT edit any files. DO NOT use any tools. Analyze this problem and respond with ONLY the solution code.

CODE RULES:
- Use markdown code blocks with language tags
- Add brief inline comments on non-obvious lines only
- Include time/space complexity as a comment at the end (e.g., # O(n) time, O(1) space)
- Prefer readability over cleverness

Output the code directly, no preamble or explanation."""
        self._process_clipboard_request(instruction)

    def _on_explain_click(self) -> None:
        if not self._pending_payload:
            return
        self._toolbar.set_processing(True)
        instruction = """You are ME in a technical interview for a Python backend/platform role. Use my resume context above. Speak as if YOU lived these experiences.

CRITICAL: THIS IS A VERBAL INTERVIEW - I will be SPEAKING your response out loud.
- NO CODE BLOCKS. Never. I cannot recite code verbally.
- Explain concepts conversationally, like you're talking to the interviewer
- A one-liner pseudocode reference is okay ("I'd use a dictionary mapping user IDs to timestamps")
- Keep responses under 30 seconds of speaking time (~75-100 words)

RESPONSE RULES:
- First-person ONLY. Say "I built..." not "You could say..."
- Lead with the answer. No preamble like "Great question!"
- Be concise. Interviewers can ask follow-ups.

FOR BEHAVIORAL QUESTIONS:
- Use STAR format (Situation, Task, Action, Result) but keep it tight
- Pull specific details from my resume: team sizes, technologies, metrics

FOR SYSTEM DESIGN QUESTIONS:
- Describe components, data flow, trade-offs in plain English
- Mention scale estimates if relevant (QPS, storage)
- Name specific technologies I'd use and why

FOR TECHNICAL CONCEPTS:
- Give a clear, concise explanation showing I understand it
- Bridge to my experience: "In my work on [project], I used this when..."

TONE: Confident peer. No hedging like "I think maybe..." - speak with authority."""
        self._process_clipboard_request(instruction)

    def _on_git_click(self) -> None:
        if not self._pending_payload or self._pending_payload.payload_type != PayloadType.IMAGE:
            return
        self._toolbar.set_processing(True)
        self._overlay.clear_and_show()
        self._overlay.start_streaming_response()
        prompt = """Analyze this screenshot of code changes/diff. Generate a conventional commit message.

Format: <type>(<scope>): <description>

Types: feat, fix, refactor, docs, test, chore, style, perf
- Keep under 72 chars
- Imperative mood ("add" not "added")
- No period at end

Output ONLY the commit message, nothing else."""
        asyncio.run_coroutine_threadsafe(
            self._claude.stream_vision_response(prompt, self._pending_payload.content),
            self._loop
        )

    def _process_clipboard_request(self, instruction: str) -> None:
        payload = self._pending_payload
        def process() -> None:
            result = self._analyzer.analyze(payload.content, instruction, payload.payload_type)
            self._signals.analysis_complete.emit(result.response)
        thread = threading.Thread(target=process, daemon=True)
        thread.start()

    def _on_analysis_complete(self, response: str) -> None:
        self._toolbar.set_processing(False)
        if self._config.stealth_enabled:
            self._overlay.show_response(response)
            self._toolbar.position_near_overlay(
                self._overlay.x(),
                self._overlay.y(),
                self._overlay.width()
            )
        else:
            self._typer.type_to_notepad(response)

    def _on_interim_update(self, text: str) -> None:
        if self._is_responding:
            return
        if text.strip():
            self._overlay.show_response(f"🎤 {text}")

    def _on_silence_detected(self) -> None:
        if not self._is_recording:
            return
        print("[DEBUG] Silence auto-detected, sending to Claude")
        self._is_recording = False
        self._toolbar.set_recording_state(False)
        asyncio.run_coroutine_threadsafe(self._loopback.stop_streaming(), self._loop)
        transcript = self._loopback.get_transcript()
        if transcript.strip():
            self._disconnect_loopback_signals()
            self._is_responding = True
            self._pending_transcript = transcript
            self._toolbar.set_audio_processing(True)
            self._overlay.show_response("Processing...")
            self._overlay.show_transcript(transcript)
            self._overlay.start_streaming_response()
            messages = (
                self._session_manager.get_messages()
                if self._session_manager.persistent_mode
                else None
            )
            asyncio.run_coroutine_threadsafe(
                self._stream_and_track_response(transcript, messages),
                self._loop
            )
        else:
            self._overlay.show_response("No speech detected")

    def _on_audio_button_click(self) -> None:
        print(f"[DEBUG] Audio button clicked, is_recording={self._is_recording}")
        if not self._is_recording:
            self._is_recording = True
            self._reconnect_loopback_signals()
            self._toolbar.set_recording_state(True)
            self._overlay.clear_and_show()
            self._overlay.show_response("Listening...")
            print("[DEBUG] Recording started, showing overlay")
            asyncio.run_coroutine_threadsafe(self._loopback.start_streaming(), self._loop)
        else:
            self._is_recording = False
            self._toolbar.set_recording_state(False)
            asyncio.run_coroutine_threadsafe(self._loopback.stop_streaming(), self._loop)

            transcript = self._loopback.get_transcript()
            print(f"[DEBUG] Recording stopped, transcript length: {len(transcript)}")
            if transcript.strip():
                self._disconnect_loopback_signals()
                self._is_responding = True
                self._pending_transcript = transcript
                self._toolbar.set_audio_processing(True)
                self._overlay.show_transcript(transcript)
                self._overlay.start_streaming_response()
                messages = (
                    self._session_manager.get_messages()
                    if self._session_manager.persistent_mode
                    else None
                )
                asyncio.run_coroutine_threadsafe(
                    self._stream_and_track_response(transcript, messages),
                    self._loop
                )
            else:
                self._overlay.show_response("No speech detected")

    def _on_final_transcript(self, transcript: str) -> None:
        if not transcript.strip():
            self._toolbar.set_audio_processing(False)
            self._overlay.show_error("No speech detected")
            return

        self._pending_transcript = transcript
        self._overlay.start_streaming_response()
        messages = (
            self._session_manager.get_messages()
            if self._session_manager.persistent_mode
            else None
        )
        asyncio.run_coroutine_threadsafe(
            self._stream_and_track_response(transcript, messages),
            self._loop
        )

    def _on_interviewer_question(self, question: str) -> None:
        if not question.strip():
            return
        self._overlay.start_streaming_response()
        asyncio.run_coroutine_threadsafe(
            self._active_provider.stream_response(question, None, self._system_prompt),
            self._loop
        )

    async def _stream_and_track_response(
        self,
        transcript: str,
        messages: list[dict[str, str]] | None,
    ) -> None:
        """Stream response from active provider and track in session if persistent mode enabled."""
        self._last_transcript = transcript
        response = await self._active_provider.stream_response(
            transcript, messages, self._system_prompt
        )
        if self._session_manager.persistent_mode and response:
            self._session_manager.add_user_message(transcript)
            self._session_manager.add_assistant_message(response)
            self._update_clear_session_action()

    def _on_response_complete(self) -> None:
        self._is_responding = False
        self._pending_transcript = ""
        self._toolbar.set_audio_processing(False)
        self._toolbar.set_processing(False)
        if self._config.overlay_timeout_ms > 0:
            QTimer.singleShot(self._config.overlay_timeout_ms, self._overlay.hide)

    def _on_streaming_error(self, error: str) -> None:
        self._is_recording = False
        self._is_responding = False
        self._reconnect_loopback_signals()
        self._toolbar.set_recording_state(False)
        self._toolbar.set_audio_processing(False)
        self._toolbar.set_processing(False)
        self._overlay.show_error(error)

    def _on_audio_complete(self, response: str) -> None:
        self._toolbar.set_audio_processing(False)
        if response:
            if self._config.stealth_enabled:
                self._overlay.show_response(response)
            else:
                self._typer.type_to_notepad(response)

    def _on_retry_hotkey(self) -> None:
        if not self._last_transcript or self._is_responding:
            return
        self._is_responding = True
        self._overlay.clear_and_show()
        self._overlay.show_transcript(self._last_transcript)
        self._overlay.start_streaming_response()
        messages = (
            self._session_manager.get_messages()
            if self._session_manager.persistent_mode
            else None
        )
        asyncio.run_coroutine_threadsafe(
            self._stream_and_track_response(self._last_transcript, messages),
            self._loop
        )

    def _on_cancel_response(self) -> None:
        if not self._is_responding:
            return
        if self._streaming_task:
            self._streaming_task.cancel()
        self._is_responding = False
        self._overlay.show_response("Cancelled - press F10 to retry")

    def _on_provider_change(self, provider_name: str) -> None:
        """Handle provider selection change from menu."""
        if provider_name == self._active_provider_name:
            return

        if provider_name == self.PROVIDER_CLAUDE:
            self._active_provider = self._claude_provider
        elif provider_name == self.PROVIDER_GEMINI_PRO:
            self._active_provider = self._gemini_pro_provider
        elif provider_name == self.PROVIDER_GEMINI_FLASH:
            self._active_provider = self._gemini_flash_provider

        self._active_provider_name = provider_name
        logger.info("AI provider changed to: %s", provider_name)

    def _on_toggle_persistent_mode(self, checked: bool) -> None:
        self._session_manager.persistent_mode = checked
        self._update_clear_session_action()
        logger.debug("Persistent mode toggled via menu: %s", checked)

    def _on_clear_session(self) -> None:
        self._session_manager.clear()
        self._update_clear_session_action()
        logger.debug("Session cleared via menu")

    def _update_clear_session_action(self) -> None:
        enabled = (
            self._session_manager.persistent_mode
            and not self._session_manager.is_empty()
        )
        self._clear_session_action.setEnabled(enabled)

    def _quit(self) -> None:
        if self._hotkey_listener is not None:
            self._hotkey_listener.stop()
        self._monitor.stop()
        asyncio.run_coroutine_threadsafe(self._loopback.shutdown(), self._loop)
        asyncio.run_coroutine_threadsafe(self._deepgram.stop_streaming(), self._loop)
        self._overlay.hide()
        self._toolbar.hide()
        self._tray.hide()
        self._loop.stop()

    def run(self) -> None:
        pass
