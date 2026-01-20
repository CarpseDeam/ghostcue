from datetime import datetime
from typing import Callable, Optional
import threading
import time
import tempfile
import os

import win32clipboard
import win32con
from PIL import ImageGrab

from contracts import ClipboardPayload, PayloadType


class ClipboardMonitor:
    def __init__(self, on_text_change: Callable[[ClipboardPayload], None], 
                 on_image_change: Callable[[ClipboardPayload], None]):
        self._on_text_change = on_text_change
        self._on_image_change = on_image_change
        self._last_text: Optional[str] = None
        self._last_image_hash: Optional[int] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._snip_mode = False
        self._temp_dir = tempfile.mkdtemp(prefix="cliphelper_")

    def _get_clipboard_text(self) -> Optional[str]:
        try:
            win32clipboard.OpenClipboard()
            try:
                if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
                    data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
                    return data
            finally:
                win32clipboard.CloseClipboard()
        except Exception:
            pass
        return None

    def _get_clipboard_image(self) -> Optional[str]:
        try:
            img = ImageGrab.grabclipboard()
            if img is not None and hasattr(img, 'save'):
                img_hash = hash(img.tobytes())
                if img_hash != self._last_image_hash:
                    self._last_image_hash = img_hash
                    path = os.path.join(self._temp_dir, f"snip_{int(time.time())}.png")
                    img.save(path, "PNG")
                    return path
        except Exception:
            pass
        return None

    def trigger_snip_mode(self):
        self._snip_mode = True
        self._last_image_hash = None

    def _poll_loop(self):
        self._last_text = self._get_clipboard_text()
        while self._running:
            time.sleep(0.1)
            
            if self._snip_mode:
                image_path = self._get_clipboard_image()
                if image_path:
                    self._snip_mode = False
                    payload = ClipboardPayload(
                        content=image_path,
                        payload_type=PayloadType.IMAGE,
                        timestamp=datetime.now()
                    )
                    self._on_image_change(payload)
                continue
            
            current_text = self._get_clipboard_text()
            if current_text and current_text != self._last_text:
                self._last_text = current_text
                payload = ClipboardPayload(
                    content=current_text.strip(),
                    payload_type=PayloadType.TEXT,
                    timestamp=datetime.now()
                )
                self._on_text_change(payload)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        try:
            for f in os.listdir(self._temp_dir):
                os.remove(os.path.join(self._temp_dir, f))
            os.rmdir(self._temp_dir)
        except Exception:
            pass
