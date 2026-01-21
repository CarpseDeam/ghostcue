import os
import wave
import tempfile
import threading
from typing import Optional

import soundcard as sc
import numpy as np

from config import Config


class AudioRecorder:
    SAMPLE_RATE = 16000
    CHANNELS = 1

    def __init__(self, config: Config):
        self._config = config
        self._recording = False
        self._frames: list[np.ndarray] = []
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start_recording(self) -> bool:
        with self._lock:
            if self._recording:
                return False
            self._recording = True
            self._frames = []

        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        return True

    def stop_recording(self) -> Optional[str]:
        with self._lock:
            if not self._recording:
                return None
            self._recording = False

        if self._thread:
            self._thread.join(timeout=2.0)

        if not self._frames:
            return None

        return self._save_wav()

    def _capture_loop(self):
        try:
            loopback = sc.get_microphone(id=str(sc.default_speaker().name), include_loopback=True)
            with loopback.recorder(samplerate=self.SAMPLE_RATE, channels=self.CHANNELS) as recorder:
                while self._recording:
                    data = recorder.record(numframes=self.SAMPLE_RATE // 10)
                    with self._lock:
                        if self._recording:
                            self._frames.append(data)
        except Exception:
            with self._lock:
                self._recording = False

    def _save_wav(self) -> str:
        os.makedirs(self._config.image_temp_dir, exist_ok=True)

        fd, path = tempfile.mkstemp(suffix='.wav', dir=self._config.image_temp_dir)
        os.close(fd)

        audio_data = np.concatenate(self._frames, axis=0)
        audio_data = np.clip(audio_data, -1.0, 1.0)
        audio_int16 = (audio_data * 32767).astype(np.int16)

        with wave.open(path, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(audio_int16.tobytes())

        return path

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording
