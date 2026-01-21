from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class PayloadType(Enum):
    TEXT = "text"
    IMAGE = "image"


@dataclass(frozen=True)
class ClipboardPayload:
    content: str
    payload_type: PayloadType
    timestamp: datetime


@dataclass(frozen=True)
class AnalysisResult:
    query: str
    response: str
    timestamp: datetime


@dataclass(frozen=True)
class AudioPayload:
    audio_path: str
    duration_seconds: float
