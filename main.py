import multiprocessing
import os
import ctypes

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

from config import Config
from app.tray import TrayApp


def hide_console():
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)


def main():
    hide_console()
    config = Config()
    app = TrayApp(config)
    app.run()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
