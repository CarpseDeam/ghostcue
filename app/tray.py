import sys
import threading
from typing import Optional, Callable

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu, QWidget, QLabel, 
    QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QIcon, QCursor, QFont, QPixmap, QPainter, QColor

from config import Config
from contracts import ClipboardPayload, PayloadType
from app.clipboard import ClipboardMonitor
from app.analyzer import Analyzer
from app.typer import HumanTyper


class SignalBridge(QObject):
    clipboard_changed = pyqtSignal(object)
    analysis_complete = pyqtSignal(str)


class FloatingWidget(QWidget):
    def __init__(self, on_submit: Callable[[str], None], config: Config):
        super().__init__()
        self._on_submit = on_submit
        self._config = config
        self._expanded = False
        self._image_mode = False
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(4)

        self._button = QLabel("?")
        self._button.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._button.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self._button.setStyleSheet("""
            QLabel {
                background-color: #4a90d9;
                color: white;
                border-radius: 14px;
            }
        """)
        self._button.setFixedSize(self._config.widget_size, self._config.widget_size)
        self._button.mousePressEvent = self._on_button_click
        self._main_layout.addWidget(self._button)

        self._input_container = QWidget()
        self._input_container.setStyleSheet("background-color: #2d2d2d; border-radius: 4px;")
        input_layout = QHBoxLayout(self._input_container)
        input_layout.setContentsMargins(4, 4, 4, 4)
        input_layout.setSpacing(4)

        self._input = QLineEdit()
        self._input.setPlaceholderText("analyze, fix, explain...")
        self._input.setStyleSheet("""
            QLineEdit {
                background-color: #3d3d3d;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 12px;
            }
        """)
        self._input.setFixedWidth(160)
        self._input.returnPressed.connect(self._submit)
        input_layout.addWidget(self._input)

        self._send_btn = QPushButton("→")
        self._send_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a90d9;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5aa0e9;
            }
        """)
        self._send_btn.setFixedSize(28, 28)
        self._send_btn.clicked.connect(self._submit)
        input_layout.addWidget(self._send_btn)

        self._input_container.hide()
        self._main_layout.addWidget(self._input_container)
        self._collapse()

    def _setup_timer(self):
        self._hide_timer = QTimer(self)
        self._hide_timer.timeout.connect(self._collapse_and_hide)
        self._hide_timer.setSingleShot(True)

    def _collapse(self):
        self._expanded = False
        self._input_container.hide()
        self.setFixedSize(self._config.widget_size, self._config.widget_size)

    def _expand(self):
        self._expanded = True
        self._input_container.show()
        self.setFixedSize(200, self._config.widget_size + 44)
        self._input.setFocus()
        self._input.clear()

    def _collapse_and_hide(self):
        self._collapse()
        self.hide()

    def _on_button_click(self, event):
        self._hide_timer.stop()
        if not self._expanded:
            self._expand()

    def _submit(self):
        instruction = self._input.text().strip()
        if not instruction:
            instruction = "analyze"
        self._collapse()
        self._on_submit(instruction)

    def show_at_cursor(self):
        self._collapse()
        pos = QCursor.pos()
        self.move(pos.x() + 15, pos.y() + 15)
        self.show()
        self._hide_timer.start(self._config.widget_timeout_ms)

    def set_processing(self, processing: bool):
        if processing:
            self._button.setText("...")
            self._button.setStyleSheet("""
                QLabel {
                    background-color: #d9a04a;
                    color: white;
                    border-radius: 14px;
                }
            """)
        else:
            self._update_button_style()

    def set_image_mode(self, image_mode: bool):
        self._image_mode = image_mode
        self._update_button_style()

    def _update_button_style(self):
        if self._image_mode:
            self._button.setText("◲")
            self._button.setStyleSheet("""
                QLabel {
                    background-color: #9b59b6;
                    color: white;
                    border-radius: 14px;
                }
            """)
        else:
            self._button.setText("?")
            self._button.setStyleSheet("""
                QLabel {
                    background-color: #4a90d9;
                    color: white;
                    border-radius: 14px;
                }
            """)

    def enterEvent(self, event):
        self._hide_timer.stop()

    def leaveEvent(self, event):
        if self.isVisible() and not self._expanded:
            self._hide_timer.start(self._config.widget_timeout_ms)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._collapse_and_hide()


class TrayApp:
    def __init__(self, config: Config):
        self._config = config
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        self._signals = SignalBridge()
        self._signals.clipboard_changed.connect(self._on_clipboard_signal)
        self._signals.analysis_complete.connect(self._on_analysis_complete)

        self._analyzer = Analyzer()
        self._typer = HumanTyper()
        self._pending_payload: Optional[ClipboardPayload] = None

        self._setup_tray()
        self._setup_widget()
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

    def _setup_clipboard_monitor(self):
        self._monitor = ClipboardMonitor(self._on_clipboard_change, self._on_clipboard_change)
        self._monitor.start()

    def _on_clipboard_change(self, payload: ClipboardPayload):
        self._signals.clipboard_changed.emit(payload)

    def _on_clipboard_signal(self, payload: ClipboardPayload):
        self._pending_payload = payload
        self._widget.set_processing(False)
        self._widget.set_image_mode(payload.payload_type == PayloadType.IMAGE)
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
        self._typer.type_to_notepad(response)

    def _quit(self):
        self._monitor.stop()
        self._tray.hide()
        self._app.quit()

    def run(self):
        sys.exit(self._app.exec())
