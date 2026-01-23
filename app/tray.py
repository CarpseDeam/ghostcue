from __future__ import annotations

import asyncio
import subprocess
import threading
from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget,
    QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QPoint
from PyQt6.QtGui import QIcon, QCursor, QPixmap, QPainter, QColor

from config import Config
from contracts import ClipboardPayload, PayloadType
from app.clipboard import ClipboardMonitor
from app.analyzer import Analyzer
from app.typer import HumanTyper
from app.stealth import make_stealth
from app.overlay import StealthOverlay
from app.deepgram_client import DeepgramStreamingClient
from app.claude_client import ClaudeStreamingClient


class SignalBridge(QObject):
    clipboard_changed = pyqtSignal(object)
    analysis_complete = pyqtSignal(str)
    audio_complete = pyqtSignal(str)
    streaming_error = pyqtSignal(str)


class FloatingWidget(QWidget):
    def __init__(self, on_submit: Callable[[str], None], config: Config) -> None:
        super().__init__()
        self._on_submit = on_submit
        self._config = config
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self._container = QWidget()
        self._container.setStyleSheet("background-color: #2d2d2d; border-radius: 6px;")

        layout = QHBoxLayout(self._container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self._solve_btn = QPushButton("S")
        self._solve_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
        """)
        self._solve_btn.setFixedSize(28, 28)
        self._solve_btn.clicked.connect(self._on_solve)
        layout.addWidget(self._solve_btn)

        self._explain_btn = QPushButton("A")
        self._explain_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5dade2;
            }
        """)
        self._explain_btn.setFixedSize(28, 28)
        self._explain_btn.clicked.connect(self._on_explain)
        layout.addWidget(self._explain_btn)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

    def _setup_timer(self) -> None:
        self._hide_timer = QTimer(self)
        self._hide_timer.timeout.connect(self.hide)
        self._hide_timer.setSingleShot(True)

    def _on_solve(self) -> None:
        self._hide_timer.stop()
        self._on_submit("DO NOT edit any files. DO NOT use any tools. Just analyze this problem and respond with ONLY the solution code. Output the code directly in your response, nothing else.")

    def _on_explain(self) -> None:
        self._hide_timer.stop()
        self._on_submit("DO NOT edit any files. DO NOT use any tools. Explain this problem clearly and teach me the concept. Output your explanation directly in your response.")

    def show_at_cursor(self) -> None:
        pos = QCursor.pos()
        self.move(pos.x() + 15, pos.y() + 15)
        self.adjustSize()
        self.show()
        make_stealth(self)
        self._hide_timer.start(self._config.widget_timeout_ms)

    def set_processing(self, processing: bool) -> None:
        self._solve_btn.setEnabled(not processing)
        self._explain_btn.setEnabled(not processing)
        if processing:
            self._solve_btn.setText("...")
            self._explain_btn.setText("...")
        else:
            self._solve_btn.setText("S")
            self._explain_btn.setText("A")

    def enterEvent(self, event) -> None:
        self._hide_timer.stop()

    def leaveEvent(self, event) -> None:
        if self.isVisible():
            self._hide_timer.start(self._config.widget_timeout_ms)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()


class FloatingToolbar(QWidget):
    def __init__(self, on_audio_click: Optional[Callable[[], None]] = None) -> None:
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._on_audio_callback = on_audio_click
        self._is_recording = False
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

        self._snip_btn = QPushButton("\u25f2")
        self._snip_btn.setStyleSheet("""
            QPushButton {
                background-color: #9b59b6;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #a569c6;
            }
        """)
        self._snip_btn.setFixedSize(28, 28)
        self._snip_btn.clicked.connect(self._on_snip_click)
        layout.addWidget(self._snip_btn)

        self._audio_btn = QPushButton("\u25cf")
        self._audio_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 4px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f75c4c;
            }
        """)
        self._audio_btn.setFixedSize(28, 28)
        self._audio_btn.setToolTip("Click to record")
        self._audio_btn.clicked.connect(self._on_audio_click)
        layout.addWidget(self._audio_btn)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

    def _on_snip_click(self) -> None:
        subprocess.run(['explorer', 'ms-screenclip:'], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def _on_audio_click(self) -> None:
        if self._on_audio_callback:
            self._on_audio_callback()

    def set_recording_state(self, is_recording: bool) -> None:
        self._is_recording = is_recording
        if is_recording:
            self._audio_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ff6b6b;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #ff8b8b;
                }
            """)
            self._audio_btn.setToolTip("Recording... Click to stop")
        else:
            self._audio_btn.setStyleSheet("""
                QPushButton {
                    background-color: #e74c3c;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
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
            self._audio_btn.setText("\u25cf")

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
        self._pending_payload: Optional[ClipboardPayload] = None
        self._streaming_task: Optional[asyncio.Task] = None

        self._overlay = StealthOverlay(config)

        self._deepgram = DeepgramStreamingClient()
        self._claude = ClaudeStreamingClient()
        self._connect_streaming_signals()

        self._setup_tray()
        self._setup_widget()
        self._setup_toolbar()
        self._setup_clipboard_monitor()

    def _connect_streaming_signals(self) -> None:
        self._deepgram.interim_transcript.connect(self._overlay.interim_transcript.emit)
        self._deepgram.final_transcript.connect(self._on_final_transcript)
        self._deepgram.error_occurred.connect(self._on_streaming_error)

        self._claude.text_chunk.connect(self._overlay.text_chunk_received.emit)
        self._claude.response_complete.connect(self._on_response_complete)
        self._claude.error_occurred.connect(self._on_streaming_error)

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

    def _setup_widget(self) -> None:
        self._widget = FloatingWidget(self._on_widget_submit, self._config)

    def _setup_toolbar(self) -> None:
        self._toolbar = FloatingToolbar(on_audio_click=self._on_audio_button_click)
        self._toolbar.show_in_corner()

    def _setup_clipboard_monitor(self) -> None:
        self._monitor = ClipboardMonitor(self._on_clipboard_change)
        self._monitor.start()

    def _on_clipboard_change(self, payload: ClipboardPayload) -> None:
        self._signals.clipboard_changed.emit(payload)

    def _on_clipboard_signal(self, payload: ClipboardPayload) -> None:
        self._pending_payload = payload
        self._widget.set_processing(False)
        self._widget.show_at_cursor()

    def _on_widget_submit(self, instruction: str) -> None:
        if not self._pending_payload:
            return

        self._widget.set_processing(True)
        payload = self._pending_payload
        self._widget.hide()

        def process() -> None:
            result = self._analyzer.analyze(payload.content, instruction, payload.payload_type)
            self._signals.analysis_complete.emit(result.response)

        thread = threading.Thread(target=process, daemon=True)
        thread.start()

    def _on_analysis_complete(self, response: str) -> None:
        self._widget.set_processing(False)
        if self._config.stealth_enabled:
            self._overlay.show_response(response)
        else:
            self._typer.type_to_notepad(response)

    def _on_audio_button_click(self) -> None:
        if not self._is_recording:
            self._is_recording = True
            self._toolbar.set_recording_state(True)
            self._overlay.clear_and_show()
            asyncio.run_coroutine_threadsafe(self._deepgram.start_streaming(), self._loop)
        else:
            self._is_recording = False
            self._toolbar.set_recording_state(False)
            self._toolbar.set_audio_processing(True)
            asyncio.run_coroutine_threadsafe(self._deepgram.stop_streaming(), self._loop)

    def _on_final_transcript(self, transcript: str) -> None:
        if not transcript.strip():
            self._toolbar.set_audio_processing(False)
            self._overlay.show_error("No speech detected")
            return

        self._overlay.start_streaming_response()
        asyncio.run_coroutine_threadsafe(self._claude.stream_response(transcript), self._loop)

    def _on_response_complete(self) -> None:
        self._toolbar.set_audio_processing(False)
        if self._config.overlay_timeout_ms > 0:
            QTimer.singleShot(self._config.overlay_timeout_ms, self._overlay.hide)

    def _on_streaming_error(self, error: str) -> None:
        self._is_recording = False
        self._toolbar.set_recording_state(False)
        self._toolbar.set_audio_processing(False)
        self._overlay.show_error(error)

    def _on_audio_complete(self, response: str) -> None:
        self._toolbar.set_audio_processing(False)
        if response:
            if self._config.stealth_enabled:
                self._overlay.show_response(response)
            else:
                self._typer.type_to_notepad(response)

    def _quit(self) -> None:
        self._monitor.stop()
        asyncio.run_coroutine_threadsafe(self._deepgram.stop_streaming(), self._loop)
        self._overlay.hide()
        self._toolbar.hide()
        self._tray.hide()
        self._loop.stop()

    def run(self) -> None:
        pass
