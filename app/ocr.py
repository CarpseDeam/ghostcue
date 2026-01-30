import asyncio
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

from PIL import Image

try:
    import winocr
    WINOCR_AVAILABLE = True
except ImportError as e:
    WINOCR_AVAILABLE = False
    WINOCR_ERROR = str(e)


@dataclass(frozen=True)
class OCRResult:
    text: str
    success: bool
    error: Optional[str] = None


class WindowsOCR:
    def __init__(self, language: str = "en"):
        self._language = language

    async def _extract_async(self, image_path: Path) -> OCRResult:
        try:
            image = Image.open(image_path)
            result = await winocr.recognize_pil(image, lang=self._language)
            
            if result and result.text:
                return OCRResult(text=result.text.strip(), success=True)
            
            return OCRResult(text="", success=False, error="No text detected in image")
            
        except FileNotFoundError:
            return OCRResult(text="", success=False, error=f"Image not found: {image_path}")
        except Exception as e:
            return OCRResult(text="", success=False, error=str(e))

    def extract_text(self, image_path: str) -> OCRResult:
        if not WINOCR_AVAILABLE:
            return OCRResult(text="", success=False, error=f"winocr not available: {WINOCR_ERROR}")

        path = Path(image_path)

        if not path.exists():
            return OCRResult(text="", success=False, error=f"Image not found: {image_path}")

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._extract_async(path))
        except Exception as e:
            return OCRResult(text="", success=False, error=str(e))
        finally:
            loop.close()
