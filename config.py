import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    widget_timeout_ms: int = 5000
    widget_size: int = 28
    typing_speed: float = 0.045
    typing_variance: float = 0.025
    image_temp_dir: str = tempfile.gettempdir()
    image_widget_color: str = "#9b59b6"
