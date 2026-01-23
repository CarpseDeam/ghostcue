from __future__ import annotations

import asyncio
import ctypes
import multiprocessing
import os
import sys

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

from dotenv import load_dotenv

load_dotenv()

import qasync
from PyQt6.QtWidgets import QApplication

from config import Config
from app.tray import TrayApp


def hide_console() -> None:
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)


def main() -> None:
    hide_console()

    config = Config()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    tray = TrayApp(config, loop)

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
