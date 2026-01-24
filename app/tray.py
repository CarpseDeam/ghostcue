from __future__ import annotations

import asyncio
import subprocess
import threading
from typing import Optional, Callable

from pynput import keyboard as pynput_keyboard

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor

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


class SignalBridge(QObject):
    clipboard_changed = pyqtSignal(object)
    analysis_complete = pyqtSignal(str)
    audio_complete = pyqtSignal(str)
    streaming_error = pyqtSignal(str)


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
    def __init__(self, config: Config, loop: asyncio.AbstractEventLoop) -> None:
        self._config = config
        self._loop = loop
        self._app = QApplication.instance()

        self._signals = SignalBridge()
        self._signals.clipboard_changed.connect(self._on_clipboard_signal)
        self._signals.analysis_complete.connect(self._on_analysis_complete)
        self._signals.audio_complete.connect(self._on_audio_complete)
        self._signals.streaming_error.connect(self._on_streaming_error)

        self._analyzer = Analyzer()
        self._typer = HumanTyper()
        self._is_recording = False
        self._is_responding = False
        self._f9_pressed: bool = False
        self._pending_payload: Optional[ClipboardPayload] = None
        self._streaming_task: Optional[asyncio.Task] = None
        self._hotkey_listener: Optional[pynput_keyboard.Listener] = None

        self._overlay = StealthOverlay(config)

        self._deepgram = DeepgramStreamingClient()
        self._claude = ClaudeStreamingClient()
        self._loopback = LoopbackStreamingClient()
        self._loopback.set_silence_threshold(
            self._config.silence_threshold_ms,
            self._config.question_silence_threshold_ms
        )
        self._connect_streaming_signals()
        self._connect_loopback_signals()

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
        self._loopback.silence_detected.connect(self._on_silence_detected)

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
                if key == pynput_keyboard.Key.f9 and not self._f9_pressed:
                    self._f9_pressed = True
                    print("[DEBUG] F9 hotkey pressed!")
                    QTimer.singleShot(0, self._on_audio_button_click)
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
            print("[DEBUG] F9 hotkey registered via pynput")
        except Exception as e:
            print(f"[DEBUG] Failed to register F9 hotkey: {e}")

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
        instruction = """DO NOT edit any files. DO NOT use any tools. Explain this problem clearly.

RESPONSE RULES:
- Lead with the answer, no preamble like "Great question!"
- Keep explanations to 2-3 sentences per concept
- For behavioral questions: use STAR format (Situation, Task, Action, Result) but keep it tight
- For code concepts: include a minimal example in markdown code blocks
- Sound confident, not arrogant

Output your explanation directly."""
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
            self._toolbar.set_audio_processing(True)
            self._overlay.show_response("Processing...")
            self._overlay.start_streaming_response()
            asyncio.run_coroutine_threadsafe(
                self._claude.stream_response(transcript),
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
                self._toolbar.set_audio_processing(True)
                self._overlay.start_streaming_response()
                asyncio.run_coroutine_threadsafe(
                    self._claude.stream_response(transcript),
                    self._loop
                )
            else:
                self._overlay.show_response("No speech detected")

    def _on_final_transcript(self, transcript: str) -> None:
        if not transcript.strip():
            self._toolbar.set_audio_processing(False)
            self._overlay.show_error("No speech detected")
            return

        self._overlay.start_streaming_response()
        asyncio.run_coroutine_threadsafe(self._claude.stream_response(transcript), self._loop)

    def _on_interviewer_question(self, question: str) -> None:
        if not question.strip():
            return
        self._overlay.start_streaming_response()
        asyncio.run_coroutine_threadsafe(
            self._claude.stream_response(question),
            self._loop
        )

    def _on_response_complete(self) -> None:
        self._is_responding = False
        self._toolbar.set_audio_processing(False)
        self._toolbar.set_processing(False)
        if self._config.overlay_timeout_ms > 0:
            QTimer.singleShot(self._config.overlay_timeout_ms, self._overlay.hide)

    def _on_streaming_error(self, error: str) -> None:
        self._is_recording = False
        self._is_responding = False
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
