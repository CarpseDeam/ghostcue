from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Optional

import pyaudio
import websockets
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass(frozen=True)
class DeepgramConfig:
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 8000
    encoding: str = "linear16"
    model: str = "nova-3"
    language: str = "en"
    interim_results: bool = True
    endpointing_ms: int = 300
    smart_format: bool = True
    punctuate: bool = True


class DeepgramStreamingClient(QObject):
    interim_transcript = pyqtSignal(str)
    final_transcript = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, config: Optional[DeepgramConfig] = None) -> None:
        super().__init__()
        self._config = config or DeepgramConfig()
        self._api_key = os.getenv("DEEPGRAM_API_KEY", "")
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._pyaudio: Optional[pyaudio.PyAudio] = None
        self._stream: Optional[pyaudio.Stream] = None
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._accumulated_transcript = ""

    def _build_url(self) -> str:
        params = [
            f"encoding={self._config.encoding}",
            f"sample_rate={self._config.sample_rate}",
            f"channels={self._config.channels}",
            f"model={self._config.model}",
            f"language={self._config.language}",
            f"punctuate={str(self._config.punctuate).lower()}",
            f"interim_results={str(self._config.interim_results).lower()}",
            f"endpointing={self._config.endpointing_ms}",
            f"smart_format={str(self._config.smart_format).lower()}",
        ]
        return f"wss://api.deepgram.com/v1/listen?{'&'.join(params)}"

    def _audio_callback(
        self,
        in_data: Optional[bytes],
        frame_count: int,
        time_info: dict,
        status: int,
    ) -> tuple[None, int]:
        if in_data and self._running:
            self._audio_queue.put_nowait(in_data)
        return (None, pyaudio.paContinue)

    def _start_audio(self) -> None:
        self._pyaudio = pyaudio.PyAudio()
        self._stream = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=self._config.channels,
            rate=self._config.sample_rate,
            input=True,
            frames_per_buffer=self._config.chunk_size,
            stream_callback=self._audio_callback,
        )
        self._stream.start_stream()

    def _stop_audio(self) -> None:
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None

    async def _sender(self, ws: websockets.WebSocketClientProtocol) -> None:
        try:
            while self._running:
                try:
                    data = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                    await ws.send(data)
                except asyncio.TimeoutError:
                    continue
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.error_occurred.emit(f"Sender error: {e}")

    async def _receiver(self, ws: websockets.WebSocketClientProtocol) -> None:
        try:
            async for msg in ws:
                if not self._running:
                    break
                data = json.loads(msg)

                if "channel" in data:
                    alternatives = data["channel"].get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        if transcript.strip():
                            is_final = data.get("is_final", False)
                            if is_final:
                                self._accumulated_transcript += transcript + " "
                                self.final_transcript.emit(self._accumulated_transcript.strip())
                            else:
                                combined = self._accumulated_transcript + transcript
                                self.interim_transcript.emit(combined.strip())

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.error_occurred.emit(f"Receiver error: {e}")

    async def start_streaming(self) -> None:
        if not self._api_key:
            self.error_occurred.emit("DEEPGRAM_API_KEY not set")
            return

        self._running = True
        self._accumulated_transcript = ""

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        url = self._build_url()
        headers = {"Authorization": f"Token {self._api_key}"}

        try:
            self._websocket = await websockets.connect(url, additional_headers=headers)
            self._start_audio()

            sender_task = asyncio.create_task(self._sender(self._websocket))
            receiver_task = asyncio.create_task(self._receiver(self._websocket))

            await asyncio.gather(sender_task, receiver_task)

        except websockets.exceptions.InvalidStatus as e:
            error_msg = f"Connection failed: {e}"
            if hasattr(e, 'response') and e.response.status_code == 401:
                error_msg = "Invalid Deepgram API key"
            self.error_occurred.emit(error_msg)
        except Exception as e:
            self.error_occurred.emit(f"Streaming error: {e}")
        finally:
            self._stop_audio()
            self._running = False

    async def stop_streaming(self) -> None:
        self._running = False
        self._stop_audio()

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None

    def get_transcript(self) -> str:
        return self._accumulated_transcript.strip()
