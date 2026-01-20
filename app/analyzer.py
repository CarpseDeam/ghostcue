import subprocess
from datetime import datetime

from contracts import AnalysisResult, PayloadType


class Analyzer:
    CLAUDE_PATH = r"C:\Users\carps\AppData\Roaming\npm\claude.cmd"

    def analyze(self, content: str, instruction: str, payload_type: PayloadType) -> AnalysisResult:
        if payload_type == PayloadType.IMAGE:
            prompt = f"{instruction}: {content}"
        else:
            prompt = f"{instruction}:\n\n{content}"
        
        try:
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
        except FileNotFoundError:
            response = "[Error: Claude CLI not found]"
        except Exception as e:
            response = f"[Error: {str(e)}]"

        return AnalysisResult(
            query=content if payload_type == PayloadType.TEXT else "[Image]",
            response=response,
            timestamp=datetime.now()
        )
