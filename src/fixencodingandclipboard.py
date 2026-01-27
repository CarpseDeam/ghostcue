"""Fix encoding and clipboard utilities."""
from __future__ import annotations

import re
from pathlib import Path


UNICODE_TO_ASCII: dict[str, str] = {
    "\u2014": "-",      # em dash
    "\u2013": "-",      # en dash
    "\u2018": "'",      # left single quote
    "\u2019": "'",      # right single quote
    "\u201c": '"',      # left double quote
    "\u201d": '"',      # right double quote
    "\u2026": "...",    # ellipsis
    "\u2022": "*",      # bullet
    "\u00b7": "*",      # middle dot
    "\u2248": "~",      # approximately equal
    "\u2502": "|",      # box drawing vertical
    "\u2500": "-",      # box drawing horizontal
    "\u00a0": " ",      # non-breaking space
}


def replace_unicode_with_ascii(text: str) -> str:
    """Replace common unicode characters with ASCII equivalents."""
    result = text
    for unicode_char, ascii_char in UNICODE_TO_ASCII.items():
        result = result.replace(unicode_char, ascii_char)
    return result


def fix_file_encoding(file_path: Path) -> bool:
    """Read a file, replace unicode with ASCII, and write back.

    Returns True if file was modified, False otherwise.
    """
    content = file_path.read_text(encoding="utf-8")
    fixed_content = replace_unicode_with_ascii(content)
    if fixed_content != content:
        file_path.write_text(fixed_content, encoding="utf-8")
        return True
    return False


def is_ascii_only(text: str) -> bool:
    """Check if text contains only ASCII characters."""
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def copy_text_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard using PyQt6.

    Returns True if successful, False otherwise.
    """
    try:
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(text)
        return True
    except Exception:
        return False


def get_clipboard_text() -> str | None:
    """Get text from system clipboard.

    Returns clipboard text or None if unavailable.
    """
    try:
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return None
        return clipboard.text()
    except Exception:
        return None
