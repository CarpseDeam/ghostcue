import os
import httpx


class Transcriber:
    API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
    
    def __init__(self):
        self._api_key = os.environ.get("GROQ_API_KEY", "")
    
    def transcribe(self, audio_path: str) -> str:
        if not self._api_key:
            return "[Error: GROQ_API_KEY not set]"
        
        try:
            with open(audio_path, "rb") as f:
                files = {"file": ("audio.wav", f, "audio/wav")}
                data = {"model": "whisper-large-v3-turbo", "response_format": "text"}
                headers = {"Authorization": f"Bearer {self._api_key}"}
                
                response = httpx.post(
                    self.API_URL,
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    return response.text.strip()
                else:
                    return f"[Error: {response.status_code}]"
                    
        except Exception as e:
            return f"[Error: {str(e)}]"
