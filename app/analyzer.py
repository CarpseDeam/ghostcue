import subprocess
from datetime import datetime

from contracts import AnalysisResult, PayloadType
from app.ocr import WindowsOCR


class Analyzer:
    CLAUDE_PATH = r"C:\Users\carps\AppData\Roaming\npm\claude.cmd"

    def __init__(self):
        self._ocr = WindowsOCR()

    def analyze(self, content: str, instruction: str, payload_type: PayloadType) -> AnalysisResult:
        try:
            if payload_type == PayloadType.IMAGE:
                ocr_result = self._ocr.extract_text(content)
                
                if not ocr_result.success:
                    return AnalysisResult(
                        query="[Image]",
                        response=f"[OCR Error: {ocr_result.error}]",
                        timestamp=datetime.now()
                    )
                
                if not ocr_result.text:
                    return AnalysisResult(
                        query="[Image]",
                        response="[Error: No text detected in image]",
                        timestamp=datetime.now()
                    )
                
                prompt = f"{instruction}:\n\n{ocr_result.text}"
                query_display = "[Image → OCR]"
            else:
                prompt = f"{instruction}:\n\n{content}"
                query_display = content

            process = subprocess.Popen(
                [self.CLAUDE_PATH],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=prompt, timeout=120)

            response = stdout.strip() if stdout.strip() else stderr.strip()
            if not response:
                response = "[Error: Empty response from Claude]"

        except subprocess.TimeoutExpired:
            process.kill()
            response = "[Error: Claude CLI timed out]"
            query_display = content if payload_type == PayloadType.TEXT else "[Image]"
        except FileNotFoundError:
            response = "[Error: Claude CLI not found]"
            query_display = content if payload_type == PayloadType.TEXT else "[Image]"
        except Exception as e:
            response = f"[Error: {str(e)}]"
            query_display = content if payload_type == PayloadType.TEXT else "[Image]"

        return AnalysisResult(
            query=query_display,
            response=response,
            timestamp=datetime.now()
        )
