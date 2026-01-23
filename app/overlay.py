from __future__ import annotations

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QApplication, QSizeGrip
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QFont

from config import Config
from app.stealth import make_stealth


class StealthOverlay(QWidget):
    interim_transcript = pyqtSignal(str)
    text_chunk_received = pyqtSignal(str)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self._drag_pos: QPoint | None = None
        self._resize_edge: str | None = None
        self._response_text = ""
        self._setup_ui()
        self._setup_timer()
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.interim_transcript.connect(self._show_interim)
        self.text_chunk_received.connect(self._append_text)

    def _setup_ui(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(300, 150)

        bg_alpha = int(self._config.overlay_opacity * 255)

        self._container = QWidget()
        self._container.setStyleSheet(f"""
            QWidget {{
                background-color: rgba(30, 30, 30, {bg_alpha});
                border-radius: 8px;
            }}
        """)

        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(12, 8, 12, 12)
        container_layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addStretch()

        self._dismiss_btn = QPushButton("\u00d7")
        self._dismiss_btn.setFixedSize(20, 20)
        self._dismiss_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #666666;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)
        self._dismiss_btn.clicked.connect(self.hide)
        header_layout.addWidget(self._dismiss_btn)

        container_layout.addLayout(header_layout)

        self._interim_label = QLabel()
        self._interim_label.setWordWrap(True)
        self._interim_label.setStyleSheet("""
            QLabel {
                color: #888888;
                background-color: transparent;
                font-style: italic;
                padding: 4px;
            }
        """)
        font = QFont()
        font.setPointSize(self._config.overlay_font_size - 1)
        self._interim_label.setFont(font)
        self._interim_label.hide()
        container_layout.addWidget(self._interim_label)

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: rgba(60, 60, 60, 100);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: rgba(150, 150, 150, 150);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        self._text_label = QLabel()
        self._text_label.setWordWrap(True)
        self._text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._text_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                background-color: transparent;
                line-height: 1.4;
            }
        """)
        font = QFont()
        font.setPointSize(self._config.overlay_font_size)
        self._text_label.setFont(font)

        self._scroll_area.setWidget(self._text_label)
        container_layout.addWidget(self._scroll_area)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._container)

        self._size_grip = QSizeGrip(self)
        self._size_grip.setStyleSheet("background: transparent;")

    def _setup_timer(self) -> None:
        self._hide_timer = QTimer(self)
        self._hide_timer.timeout.connect(self.hide)
        self._hide_timer.setSingleShot(True)

    def _show_interim(self, text: str) -> None:
        self._interim_label.setText(f'"{text}"')
        self._interim_label.show()

    def _append_text(self, text: str) -> None:
        self._response_text += text
        self._text_label.setText(self._response_text)
        scrollbar = self._scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_and_show(self) -> None:
        self._response_text = ""
        self._text_label.setText("")
        self._interim_label.setText("")
        self._interim_label.show()
        self._position_top_center()
        self.resize(self._config.overlay_width, 400)
        self.show()
        make_stealth(self)

    def start_streaming_response(self) -> None:
        self._interim_label.hide()
        self._response_text = ""
        self._text_label.setText("Thinking...")

    def show_response(self, text: str) -> None:
        self._interim_label.hide()
        self._response_text = text
        self._text_label.setText(text)
        self._position_top_center()
        self.resize(self._config.overlay_width, 400)
        self.show()
        make_stealth(self)
        if self._config.overlay_timeout_ms > 0:
            self._hide_timer.start(self._config.overlay_timeout_ms)

    def show_error(self, error: str) -> None:
        self._interim_label.hide()
        self._response_text = f"[Error: {error}]"
        self._text_label.setText(self._response_text)
        self._text_label.setStyleSheet("""
            QLabel {
                color: #ff6b6b;
                background-color: transparent;
                line-height: 1.4;
            }
        """)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._size_grip.move(self.width() - 16, self.height() - 16)

    def _position_top_center(self) -> None:
        screen = QApplication.primaryScreen().geometry()
        x = screen.center().x() - self._config.overlay_width // 2
        y = screen.top() + 100
        self.move(x, y)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

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

    def enterEvent(self, event) -> None:
        self._hide_timer.stop()

    def leaveEvent(self, event) -> None:
        if self.isVisible() and self._config.overlay_timeout_ms > 0:
            self._hide_timer.start(self._config.overlay_timeout_ms)
