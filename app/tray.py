import os
import subprocess
import sys
import threading
import multiprocessing
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
from app.transcriber import Transcriber


class SignalBridge(QObject):
    clipboard_changed = pyqtSignal(object)
    analysis_complete = pyqtSignal(str)
    audio_complete = pyqtSignal(str)


class FloatingWidget(QWidget):
    def __init__(self, on_submit: Callable[[str], None], config: Config):
        super().__init__()
        self._on_submit = on_submit
        self._config = config
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
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

    def _setup_timer(self):
        self._hide_timer = QTimer(self)
        self._hide_timer.timeout.connect(self.hide)
        self._hide_timer.setSingleShot(True)

    def _on_solve(self):
        self._hide_timer.stop()
        self._on_submit("DO NOT edit any files. DO NOT use any tools. Just analyze this problem and respond with ONLY the solution code. Output the code directly in your response, nothing else.")

    def _on_explain(self):
        self._hide_timer.stop()
        self._on_submit("DO NOT edit any files. DO NOT use any tools. Explain this problem clearly and teach me the concept. Output your explanation directly in your response.")

    def show_at_cursor(self):
        pos = QCursor.pos()
        self.move(pos.x() + 15, pos.y() + 15)
        self.adjustSize()
        self.show()
        make_stealth(self)
        self._hide_timer.start(self._config.widget_timeout_ms)

    def set_processing(self, processing: bool):
        self._solve_btn.setEnabled(not processing)
        self._explain_btn.setEnabled(not processing)
        if processing:
            self._solve_btn.setText("...")
            self._explain_btn.setText("...")
        else:
            self._solve_btn.setText("S")
            self._explain_btn.setText("A")

    def enterEvent(self, event):
        self._hide_timer.stop()

    def leaveEvent(self, event):
        if self.isVisible():
            self._hide_timer.start(self._config.widget_timeout_ms)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()


class FloatingToolbar(QWidget):
    def __init__(self, on_audio_click: Optional[Callable[[], None]] = None):
        super().__init__()
        self._drag_pos: QPoint | None = None
        self._on_audio_callback = on_audio_click
        self._is_recording = False
        self._setup_ui()

    def _setup_ui(self):
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

        self._snip_btn = QPushButton("◲")
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

        self._audio_btn = QPushButton("●")
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

    def _on_snip_click(self):
        subprocess.run(['explorer', 'ms-screenclip:'], shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

    def _on_audio_click(self):
        if self._on_audio_callback:
            self._on_audio_callback()

    def set_recording_state(self, is_recording: bool):
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

    def set_audio_processing(self, processing: bool):
        self._audio_btn.setEnabled(not processing)
        if processing:
            self._audio_btn.setText("...")
        else:
            self._audio_btn.setText("\u25cf")

    def show_in_corner(self):
        self.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        x = screen.left() + 20
        y = screen.bottom() - self.height() - 20
        self.move(x, y)
        self.show()
        make_stealth(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


class TrayApp:
    def __init__(self, config: Config):
        self._config = config
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        self._signals = SignalBridge()
        self._signals.clipboard_changed.connect(self._on_clipboard_signal)
        self._signals.analysis_complete.connect(self._on_analysis_complete)
        self._signals.audio_complete.connect(self._on_audio_complete)

        self._transcriber = Transcriber()
        self._analyzer = Analyzer()
        self._typer = HumanTyper()
        self._is_recording = False
        self._pending_payload: Optional[ClipboardPayload] = None

        self._audio_process: Optional[multiprocessing.Process] = None
        self._command_queue: Optional[multiprocessing.Queue] = None
        self._result_queue: Optional[multiprocessing.Queue] = None

        self._overlay = StealthOverlay(config)

        self._start_audio_worker()

        self._setup_tray()
        self._setup_widget()
        self._setup_toolbar()
        self._setup_clipboard_monitor()

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

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self._create_icon(), self._app)
        self._tray.setToolTip("Clipboard Helper")

        menu = QMenu()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self._quit)

        self._tray.setContextMenu(menu)
        self._tray.show()

    def _setup_widget(self):
        self._widget = FloatingWidget(self._on_widget_submit, self._config)

    def _setup_toolbar(self):
        self._toolbar = FloatingToolbar(on_audio_click=self._on_audio_button_click)
        self._toolbar.show_in_corner()

    def _setup_clipboard_monitor(self):
        self._monitor = ClipboardMonitor(self._on_clipboard_change)
        self._monitor.start()

    def _on_clipboard_change(self, payload: ClipboardPayload):
        self._signals.clipboard_changed.emit(payload)

    def _on_clipboard_signal(self, payload: ClipboardPayload):
        self._pending_payload = payload
        self._widget.set_processing(False)
        self._widget.show_at_cursor()

    def _on_widget_submit(self, instruction: str):
        if not self._pending_payload:
            return

        self._widget.set_processing(True)
        payload = self._pending_payload
        self._widget.hide()

        def process():
            result = self._analyzer.analyze(payload.content, instruction, payload.payload_type)
            self._signals.analysis_complete.emit(result.response)

        thread = threading.Thread(target=process, daemon=True)
        thread.start()

    def _on_analysis_complete(self, response: str):
        self._widget.set_processing(False)
        if self._config.stealth_enabled:
            self._overlay.show_response(response)
        else:
            self._typer.type_to_notepad(response)

    def _start_audio_worker(self):
        from app.audio_worker import worker_main
        self._command_queue = multiprocessing.Queue()
        self._result_queue = multiprocessing.Queue()
        self._audio_process = multiprocessing.Process(
            target=worker_main,
            args=(self._command_queue, self._result_queue, self._config.image_temp_dir),
            daemon=True
        )
        self._audio_process.start()

    def _ensure_audio_worker(self):
        if self._audio_process is None or not self._audio_process.is_alive():
            self._start_audio_worker()

    def _on_audio_button_click(self):
        from app.audio_worker import AudioCommand, AudioMessage, AudioResult
        self._ensure_audio_worker()

        if not self._is_recording:
            self._command_queue.put(AudioMessage(command=AudioCommand.START))
            self._is_recording = True
            self._toolbar.set_recording_state(True)
        else:
            self._is_recording = False
            self._toolbar.set_recording_state(False)
            self._toolbar.set_audio_processing(True)

            self._command_queue.put(AudioMessage(command=AudioCommand.STOP))

            def wait_for_result():
                from app.audio_worker import AudioResult
                try:
                    result: AudioResult = self._result_queue.get(timeout=60)

                    if not result.success or not result.audio_path:
                        self._signals.audio_complete.emit("")
                        return

                    transcript = self._transcriber.transcribe(result.audio_path)

                    try:
                        os.unlink(result.audio_path)
                    except:
                        pass

                    if not transcript.strip():
                        self._signals.audio_complete.emit("")
                        return

                    analysis = self._analyzer.analyze(
                        transcript,
                        "Answer this interview question concisely and confidently.",
                        PayloadType.TEXT
                    )
                    self._signals.audio_complete.emit(analysis.response)

                except Exception:
                    self._signals.audio_complete.emit("")

            thread = threading.Thread(target=wait_for_result, daemon=True)
            thread.start()

    def _on_audio_complete(self, response: str):
        self._toolbar.set_audio_processing(False)
        if response:
            if self._config.stealth_enabled:
                self._overlay.show_response(response)
            else:
                self._typer.type_to_notepad(response)

    def _quit(self):
        self._monitor.stop()
        self._shutdown_audio_worker()
        self._overlay.hide()
        self._toolbar.hide()
        self._tray.hide()
        self._app.quit()

    def _shutdown_audio_worker(self):
        if self._audio_process and self._audio_process.is_alive():
            from app.audio_worker import AudioCommand, AudioMessage
            try:
                self._command_queue.put(AudioMessage(command=AudioCommand.SHUTDOWN))
                self._audio_process.join(timeout=2)
                if self._audio_process.is_alive():
                    self._audio_process.terminate()
            except Exception:
                pass

    def run(self):
        sys.exit(self._app.exec())
