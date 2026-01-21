import os
import wave
import tempfile
from multiprocessing import Queue
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np


class AudioCommand(Enum):
    START = "start"
    STOP = "stop"
    SHUTDOWN = "shutdown"


@dataclass
class AudioMessage:
    command: AudioCommand
    data: Optional[str] = None


@dataclass
class AudioResult:
    success: bool
    audio_path: str = ""
    error: str = ""


class AudioWorker:
    SAMPLE_RATE = 44100
    CHANNELS = 1
    CHUNK = 1024

    def __init__(self, command_queue: Queue, result_queue: Queue, temp_dir: str):
        self._command_queue = command_queue
        self._result_queue = result_queue
        self._temp_dir = temp_dir
        self._recording = False
        self._frames: list[bytes] = []

    def run(self):
        import pyaudio
        self._pyaudio = pyaudio
        self._pa = pyaudio.PyAudio()

        while True:
            try:
                msg: AudioMessage = self._command_queue.get()

                if msg.command == AudioCommand.SHUTDOWN:
                    self._pa.terminate()
                    break
                elif msg.command == AudioCommand.START:
                    self._start_recording()
                elif msg.command == AudioCommand.STOP:
                    self._stop_recording()

            except Exception as e:
                self._result_queue.put(AudioResult(success=False, error=str(e)))

    def _start_recording(self):
        self._recording = True
        self._frames = []

        try:
            stream = self._pa.open(
                format=self._pyaudio.paInt16,
                channels=self.CHANNELS,
                rate=self.SAMPLE_RATE,
                input=True,
                frames_per_buffer=self.CHUNK
            )

            while self._recording:
                if not self._command_queue.empty():
                    msg = self._command_queue.get_nowait()
                    if msg.command == AudioCommand.STOP:
                        self._recording = False
                        break
                    elif msg.command == AudioCommand.SHUTDOWN:
                        stream.stop_stream()
                        stream.close()
                        return

                data = stream.read(self.CHUNK, exception_on_overflow=False)
                self._frames.append(data)

            stream.stop_stream()
            stream.close()
            self._process_audio()

        except Exception as e:
            self._result_queue.put(AudioResult(success=False, error=str(e)))

    def _stop_recording(self):
        self._recording = False

    def _process_audio(self):
        if not self._frames:
            self._result_queue.put(AudioResult(success=True, audio_path=""))
            return

        wav_path = self._save_wav()
        self._result_queue.put(AudioResult(success=True, audio_path=wav_path))

    def _save_wav(self) -> str:
        os.makedirs(self._temp_dir, exist_ok=True)

        fd, path = tempfile.mkstemp(suffix='.wav', dir=self._temp_dir)
        os.close(fd)

        with wave.open(path, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)
            wf.setframerate(self.SAMPLE_RATE)
            wf.writeframes(b''.join(self._frames))

        return path


def worker_main(command_queue: Queue, result_queue: Queue, temp_dir: str):
    worker = AudioWorker(command_queue, result_queue, temp_dir)
    worker.run()
