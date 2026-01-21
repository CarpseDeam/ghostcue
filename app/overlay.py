from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QFont

from config import Config
from app.stealth import make_stealth


class StealthOverlay(QWidget):
    def __init__(self, config: Config):
        super().__init__()
        self._config = config
        self._drag_pos: QPoint | None = None
        self._setup_ui()
        self._setup_timer()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(self._config.overlay_width)

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

        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
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

    def _setup_timer(self):
        self._hide_timer = QTimer(self)
        self._hide_timer.timeout.connect(self.hide)
        self._hide_timer.setSingleShot(True)

    def show_response(self, text: str):
        self._text_label.setText(text)
        self._position_top_center()
        self.adjustSize()
        screen_height = QApplication.primaryScreen().geometry().height()
        self.setMaximumHeight(int(screen_height * 0.6))
        self.show()
        make_stealth(self)
        if self._config.overlay_timeout_ms > 0:
            self._hide_timer.start(self._config.overlay_timeout_ms)

    def _position_top_center(self):
        screen = QApplication.primaryScreen().geometry()
        x = screen.center().x() - self._config.overlay_width // 2
        y = screen.top() + 100
        self.move(x, y)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()

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

    def enterEvent(self, event):
        self._hide_timer.stop()

    def leaveEvent(self, event):
        if self.isVisible() and self._config.overlay_timeout_ms > 0:
            self._hide_timer.start(self._config.overlay_timeout_ms)
