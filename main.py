from config import Config
from app.tray import TrayApp


def main():
    config = Config()
    app = TrayApp(config)
    app.run()


if __name__ == "__main__":
    main()
