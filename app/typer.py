import subprocess
import time
import random

import pyautogui
import win32gui
import win32con


class HumanTyper:
    def __init__(self, base_delay: float = 0.018, variance: float = 0.012):
        self._base_delay = base_delay
        self._variance = variance
        self._pause_chars = {'.': 0.15, ',': 0.08, '\n': 0.2, ':': 0.1, ';': 0.1, '?': 0.15, '!': 0.15}
        self._notepad_hwnd = None

    def _get_delay(self, char: str) -> float:
        base = self._base_delay + random.uniform(-self._variance, self._variance)
        base = max(0.015, base)
        extra = self._pause_chars.get(char, 0)
        if extra:
            extra += random.uniform(-0.05, 0.1)
        return base + extra

    def _find_notepad_window(self) -> int:
        def callback(hwnd, windows):
            title = win32gui.GetWindowText(hwnd)
            if "Notepad++" in title or title.endswith("Notepad"):
                windows.append(hwnd)
            return True
        
        windows = []
        win32gui.EnumWindows(callback, windows)
        return windows[0] if windows else None

    def _focus_notepad(self):
        if self._notepad_hwnd:
            try:
                win32gui.SetForegroundWindow(self._notepad_hwnd)
            except:
                pass

    def open_notepad(self):
        try:
            subprocess.Popen([r"C:\Program Files\Notepad++\notepad++.exe"])
        except FileNotFoundError:
            subprocess.Popen(["notepad.exe"])
        time.sleep(0.8)
        self._notepad_hwnd = self._find_notepad_window()

    def type_text(self, text: str):
        pyautogui.FAILSAFE = False
        for char in text:
            self._focus_notepad()
            delay = self._get_delay(char)
            if char == '\n':
                pyautogui.press('enter')
            elif char == '\t':
                pyautogui.press('tab')
            else:
                pyautogui.typewrite(char, interval=0) if char.isascii() else pyautogui.write(char)
            time.sleep(delay)

    def type_to_notepad(self, text: str):
        self.open_notepad()
        self.type_text(text)
