import subprocess
import time

import win32api
import win32con
import win32gui
import win32clipboard


SCI_PASTE = 2179


class HumanTyper:
    def __init__(self, base_delay: float = 0.022, variance: float = 0.008, tab_width: int = 4):
        self._tab_width = tab_width
        self._notepad_hwnd = None
        self._edit_hwnd = None

    def _find_notepad_window(self) -> int:
        def callback(hwnd, windows):
            title = win32gui.GetWindowText(hwnd)
            if "Notepad++" in title or title.endswith("Notepad"):
                windows.append(hwnd)
            return True

        windows = []
        win32gui.EnumWindows(callback, windows)
        return windows[0] if windows else None

    def _find_edit_control(self, parent_hwnd: int) -> int:
        def callback(hwnd, controls):
            class_name = win32gui.GetClassName(hwnd)
            if class_name in ("Edit", "Scintilla"):
                controls.append(hwnd)
            return True

        controls = []
        win32gui.EnumChildWindows(parent_hwnd, callback, controls)
        return controls[0] if controls else parent_hwnd

    def _normalize_text(self, text: str) -> str:
        text = text.replace('\t', ' ' * self._tab_width)
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        return '\n'.join(line.rstrip() for line in text.split('\n'))

    def _set_clipboard(self, text: str):
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        finally:
            win32clipboard.CloseClipboard()

    def _send_ctrl_key(self, vk_code: int):
        win32api.SendMessage(self._notepad_hwnd, win32con.WM_KEYDOWN, win32con.VK_CONTROL, 0)
        win32api.SendMessage(self._notepad_hwnd, win32con.WM_KEYDOWN, vk_code, 0)
        win32api.SendMessage(self._notepad_hwnd, win32con.WM_KEYUP, vk_code, 0)
        win32api.SendMessage(self._notepad_hwnd, win32con.WM_KEYUP, win32con.VK_CONTROL, 0)

    def open_notepad(self):
        self._notepad_hwnd = self._find_notepad_window()
        if not self._notepad_hwnd:
            try:
                subprocess.Popen([r"C:\Program Files\Notepad++\notepad++.exe"])
            except FileNotFoundError:
                subprocess.Popen(["notepad.exe"])
            time.sleep(0.8)
            self._notepad_hwnd = self._find_notepad_window()

        if self._notepad_hwnd:
            self._edit_hwnd = self._find_edit_control(self._notepad_hwnd)

    def type_text(self, text: str):
        if not self._edit_hwnd:
            return

        text = self._normalize_text(text)
        self._set_clipboard(text)

        class_name = win32gui.GetClassName(self._edit_hwnd)
        if class_name == "Scintilla":
            win32api.SendMessage(self._edit_hwnd, SCI_PASTE, 0, 0)
        else:
            win32api.SendMessage(self._edit_hwnd, win32con.WM_PASTE, 0, 0)

    def new_tab(self):
        if self._notepad_hwnd:
            self._send_ctrl_key(ord('N'))
            time.sleep(0.1)
            self._edit_hwnd = self._find_edit_control(self._notepad_hwnd)

    def type_to_notepad(self, text: str, delay: float = 2.0):
        time.sleep(delay)
        self.open_notepad()
        self.type_text(text)
