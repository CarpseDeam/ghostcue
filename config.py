import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    widget_timeout_ms: int = 5000
    widget_size: int = 28
    button_size: int = 48
    typing_speed: float = 0.045
    typing_variance: float = 0.025
    image_temp_dir: str = os.path.join(os.path.expanduser("~"), ".cliphelper_temp")
    image_widget_color: str = "#9b59b6"
    overlay_opacity: float = 0.85
    overlay_timeout_ms: int = 0
    overlay_font_size: int = 11
    overlay_width: int = 600
    stealth_enabled: bool = True
    silence_threshold_ms: int = 1000
    question_silence_threshold_ms: int = 500
