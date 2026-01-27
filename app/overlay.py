from __future__ import annotations

import re

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication, QSizeGrip
)
from PyQt6.QtCore import Qt, QTimer, QPoint, pyqtSignal
from PyQt6.QtGui import QFont

from config import Config
from app.stealth import make_stealth

# Dark theme constants (VS Code/PyCharm style)
THEME_BACKGROUND = "#1e1e1e"
THEME_TEXT = "#d4d4d4"
THEME_TEXT_MUTED = "#888888"
THEME_BORDER = "#3c3c3c"
THEME_SELECTION = "#264f78"
THEME_CODE_TEXT = "#a8d08d"
THEME_CODE_BACKGROUND = "rgba(0, 0, 0, 0.4)"
THEME_ERROR = "#ff6b6b"
FONT_FAMILY = "'JetBrains Mono', 'Consolas', 'Courier New', monospace"
FONT_SIZE_PT = 11


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

    def _markdown_to_html(self, text: str) -> str:
        def escape_html(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        code_block_pattern = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
        parts: list[str] = []
        last_end = 0

        for match in code_block_pattern.finditer(text):
            before = text[last_end:match.start()]
            if before.strip():
                parts.append(self._process_inline_text(before))

            code_content = escape_html(match.group(2).rstrip())
            parts.append(
                f'<pre style="font-family: {FONT_FAMILY}; '
                f'background-color: {THEME_CODE_BACKGROUND}; padding: 10px; margin: 8px 0; '
                f'border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; '
                f'color: {THEME_CODE_TEXT}; font-size: {FONT_SIZE_PT - 1}pt; '
                f'line-height: 1.4;">'
                f'<code>{code_content}</code></pre>'
            )
            last_end = match.end()

        remaining = text[last_end:]
        if remaining.strip():
            parts.append(self._process_inline_text(remaining))

        return "".join(parts)

    def _process_inline_text(self, text: str) -> str:
        def escape_html(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        inline_code_pattern = re.compile(r"`([^`]+)`")
        paragraphs = text.strip().split("\n\n")
        result: list[str] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            escaped = escape_html(para)
            processed = inline_code_pattern.sub(
                f'<code style="font-family: {FONT_FAMILY}; '
                f'background-color: rgba(0, 0, 0, 0.2); padding: 2px 4px; '
                f'border-radius: 3px; color: {THEME_CODE_TEXT};">\\1</code>',
                escaped
            )
            lines = processed.replace("\n", "<br>")
            result.append(f"<p>{lines}</p>")

        return "".join(result)

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

        header_btn_style = """
            QPushButton {
                background-color: transparent;
                color: #666666;
                border: none;
                font-size: 14px;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """

        self._copy_btn = QPushButton("[C]")
        self._copy_btn.setFixedSize(24, 20)
        self._copy_btn.setStyleSheet(header_btn_style)
        self._copy_btn.setToolTip("Copy to clipboard")
        self._copy_btn.clicked.connect(self._copy_to_clipboard)
        header_layout.addWidget(self._copy_btn)

        self._dismiss_btn = QPushButton("×")
        self._dismiss_btn.setFixedSize(20, 20)
        self._dismiss_btn.setStyleSheet(header_btn_style)
        self._dismiss_btn.clicked.connect(self.hide)
        header_layout.addWidget(self._dismiss_btn)

        container_layout.addLayout(header_layout)

        self._transcript_label = QLabel()
        self._transcript_label.setWordWrap(True)
        self._transcript_label.setStyleSheet(f"""
            QLabel {{
                color: {THEME_TEXT_MUTED};
                background-color: transparent;
                padding: 4px;
            }}
        """)
        transcript_font = QFont()
        transcript_font.setFamilies(["JetBrains Mono", "Consolas", "Courier New"])
        transcript_font.setPointSize(FONT_SIZE_PT - 1)
        self._transcript_label.setFont(transcript_font)
        self._transcript_label.hide()
        container_layout.addWidget(self._transcript_label)

        self._interim_label = QLabel()
        self._interim_label.setWordWrap(True)
        self._interim_label.setStyleSheet(f"""
            QLabel {{
                color: {THEME_TEXT_MUTED};
                background-color: transparent;
                font-style: italic;
                padding: 4px;
            }}
        """)
        font = QFont()
        font.setFamilies(["JetBrains Mono", "Consolas", "Courier New"])
        font.setPointSize(FONT_SIZE_PT - 1)
        self._interim_label.setFont(font)
        self._interim_label.hide()
        container_layout.addWidget(self._interim_label)

        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._text_edit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {THEME_BACKGROUND};
                color: {THEME_TEXT};
                font-family: {FONT_FAMILY};
                font-size: {FONT_SIZE_PT}pt;
                border: 1px solid {THEME_BORDER};
                padding: 8px;
                selection-background-color: {THEME_SELECTION};
            }}
            QScrollBar:vertical {{
                background-color: {THEME_BORDER};
                width: 6px;
                border-radius: 3px;
            }}
            QScrollBar::handle:vertical {{
                background-color: rgba(150, 150, 150, 150);
                border-radius: 3px;
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        font = QFont()
        font.setFamilies(["JetBrains Mono", "Consolas", "Courier New"])
        font.setPointSize(FONT_SIZE_PT)
        self._text_edit.setFont(font)

        container_layout.addWidget(self._text_edit)

        self._cheatsheet_label = QLabel("F9 Record  |  F10 Retry  |  Esc Cancel  |  [C] Copy")
        self._cheatsheet_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cheatsheet_label.setStyleSheet(f"""
            QLabel {{
                color: {THEME_TEXT_MUTED};
                background-color: transparent;
                padding: 4px;
            }}
        """)
        cheatsheet_font = QFont()
        cheatsheet_font.setFamilies(["JetBrains Mono", "Consolas", "Courier New"])
        cheatsheet_font.setPointSize(FONT_SIZE_PT - 2)
        self._cheatsheet_label.setFont(cheatsheet_font)
        container_layout.addWidget(self._cheatsheet_label)

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

    def show_transcript(self, text: str) -> None:
        self._transcript_label.setText(text)
        self._transcript_label.show()

    def _copy_to_clipboard(self) -> None:
        text = self._response_text or self._text_edit.toPlainText()
        print(f"[DEBUG] Copy clicked, text length: {len(text) if text else 0}")
        if text:
            clipboard = QApplication.clipboard()
            clipboard.setText(text, QApplication.clipboard().Mode.Clipboard)
            print("[DEBUG] Clipboard write complete")
        else:
            print("[DEBUG] No text to copy")

    def _append_text(self, text: str) -> None:
        self._response_text += text
        self._text_edit.setHtml(self._markdown_to_html(self._response_text))
        scrollbar = self._text_edit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear_and_show(self) -> None:
        self._response_text = ""
        self._text_edit.setHtml("")
        self._interim_label.setText("")
        self._interim_label.show()
        self._position_top_center()
        self.resize(self._config.overlay_width, 400)
        self.show()
        make_stealth(self)

    def start_streaming_response(self) -> None:
        self._interim_label.hide()
        self._response_text = ""
        self._text_edit.setHtml("<p>Thinking...</p>")

    def show_response(self, text: str) -> None:
        self._interim_label.hide()
        self._response_text = text
        self._text_edit.setHtml(self._markdown_to_html(text))
        self._position_top_center()
        self.resize(self._config.overlay_width, 400)
        self.show()
        make_stealth(self)
        if self._config.overlay_timeout_ms > 0:
            self._hide_timer.start(self._config.overlay_timeout_ms)

    def show_error(self, error: str) -> None:
        self._interim_label.hide()
        self._response_text = f"[Error: {error}]"
        self._text_edit.setHtml(f'<p style="color: {THEME_ERROR};">{self._response_text}</p>')

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
            click_pos = event.position().toPoint()
            text_edit_rect = self._text_edit.geometry()
            container_pos = self._container.mapFromParent(click_pos)
            if text_edit_rect.contains(container_pos):
                self._text_edit.setFocus()
                return
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
