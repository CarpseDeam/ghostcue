import ctypes
from typing import Protocol, runtime_checkable

WDA_EXCLUDEFROMCAPTURE = 0x00000011


@runtime_checkable
class StealthCapable(Protocol):
    def winId(self) -> int: ...


def make_stealth(widget: StealthCapable) -> bool:
    try:
        hwnd = int(widget.winId())
        result = ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        return result != 0
    except Exception:
        return False
