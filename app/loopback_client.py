from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import websockets
from PyQt6.QtCore import QObject, pyqtSignal

from app.loopback_worker import MessageType, WorkerConfig, run_capture_loop


@dataclass(frozen=True)
class LoopbackConfig:
    source_sample_rate: int = 48000
    target_sample_rate: int = 16000
    channels: int = 1
    chunk_duration: float = 0.1
    encoding: str = "linear16"
    model: str = "nova-3"
    language: str = "en"
    interim_results: bool = True
    endpointing_ms: int = 800
    smart_format: bool = True
    punctuate: bool = True


class LoopbackStreamingClient(QObject):
    interim_interviewer = pyqtSignal(str)
    final_interviewer = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, config: Optional[LoopbackConfig] = None) -> None:
        super().__init__()
        self._config = config or LoopbackConfig()
        self._api_key = os.getenv("DEEPGRAM_API_KEY", "")
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._process: Optional[multiprocessing.Process] = None
        self._output_queue: Optional[multiprocessing.Queue[MessageType]] = None
        self._input_queue: Optional[multiprocessing.Queue[None]] = None
        self._running = False
        self._accumulated_transcript = ""
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._queue_reader_task: Optional[asyncio.Task[None]] = None
        self._chunks_received = 0
        self._chunks_sent = 0

    def _build_url(self) -> str:
        params = [
            f"encoding={self._config.encoding}",
            f"sample_rate={self._config.target_sample_rate}",
            f"channels={self._config.channels}",
            f"model={self._config.model}",
            f"language={self._config.language}",
            f"punctuate={str(self._config.punctuate).lower()}",
            f"interim_results={str(self._config.interim_results).lower()}",
            f"endpointing={self._config.endpointing_ms}",
            f"smart_format={str(self._config.smart_format).lower()}",
        ]
        return f"wss://api.deepgram.com/v1/listen?{'&'.join(params)}"

    def _blocking_queue_get(
        self,
        queue: multiprocessing.Queue[MessageType],
        timeout: float,
    ) -> Optional[MessageType]:
        try:
            return queue.get(timeout=timeout)
        except Exception:
            return None

    async def _queue_reader(self) -> None:
        if self._output_queue is None:
            return

        print("[DEBUG] Queue reader started")
        loop = asyncio.get_running_loop()

        while self._running:
            message = await loop.run_in_executor(
                self._executor,
                self._blocking_queue_get,
                self._output_queue,
                0.1,
            )

            if message is None:
                if self._process is not None and not self._process.is_alive():
                    print("[DEBUG] Subprocess crashed!")
                    self.error_occurred.emit("Capture subprocess crashed")
                    self._running = False
                    break
                continue

            msg_type, payload = message

            if msg_type == "audio":
                self._chunks_received += 1
                if self._chunks_received == 1:
                    print("[DEBUG] First audio chunk received from subprocess!")
                elif self._chunks_received % 50 == 0:
                    print(f"[DEBUG] Received {self._chunks_received} chunks from subprocess")
                await self._audio_queue.put(payload)
            elif msg_type == "error":
                print(f"[DEBUG] Subprocess error: {payload}")
                self.error_occurred.emit(payload)
                self._running = False
                break
            elif msg_type == "debug":
                print(f"[SUBPROCESS] {payload}")

    async def _sender(self, ws: websockets.WebSocketClientProtocol) -> None:
        print("[DEBUG] Sender task started")
        try:
            while self._running:
                try:
                    data = await asyncio.wait_for(self._audio_queue.get(), timeout=0.1)
                    self._chunks_sent += 1
                    if self._chunks_sent == 1:
                        print("[DEBUG] First audio chunk sent to Deepgram!")
                    elif self._chunks_sent % 50 == 0:
                        print(f"[DEBUG] Sent {self._chunks_sent} chunks to Deepgram")
                    await ws.send(data)
                except asyncio.TimeoutError:
                    continue
        except websockets.exceptions.ConnectionClosed:
            print("[DEBUG] WebSocket connection closed in sender")
        except Exception as e:
            print(f"[DEBUG] Sender error: {e}")
            self.error_occurred.emit(f"Sender error: {e}")

    async def _receiver(self, ws: websockets.WebSocketClientProtocol) -> None:
        print("[DEBUG] Receiver task started")
        msg_count = 0
        try:
            async for msg in ws:
                if not self._running:
                    break
                msg_count += 1
                data = json.loads(msg)

                if msg_count == 1:
                    print("[DEBUG] First Deepgram message received!")
                
                # Debug: show first few messages and any with transcripts
                if msg_count <= 3:
                    print(f"[DEBUG] Deepgram msg {msg_count}: {str(data)[:300]}")

                if "channel" in data:
                    alternatives = data["channel"].get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        if transcript.strip():
                            is_final = data.get("is_final", False)
                            if is_final:
                                self._accumulated_transcript += transcript + " "
                                self.final_interviewer.emit(self._accumulated_transcript.strip())
                            else:
                                combined = self._accumulated_transcript + transcript
                                self.interim_interviewer.emit(combined.strip())

        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.error_occurred.emit(f"Receiver error: {e}")

    async def _wait_for_ready(self, timeout: float = 5.0) -> bool:
        if self._output_queue is None:
            return False

        print("[DEBUG] Waiting for subprocess ready signal...")
        loop = asyncio.get_running_loop()
        start = loop.time()

        while loop.time() - start < timeout:
            message = await loop.run_in_executor(
                self._executor,
                self._blocking_queue_get,
                self._output_queue,
                0.1,
            )

            if message is None:
                if self._process is not None and not self._process.is_alive():
                    print("[DEBUG] Subprocess died while waiting for ready")
                    return False
                continue

            msg_type, payload = message

            if msg_type == "ready":
                print("[DEBUG] Ready signal received!")
                return True
            elif msg_type == "error":
                print(f"[DEBUG] Error during init: {payload}")
                self.error_occurred.emit(payload)
                return False
            elif msg_type == "debug":
                print(f"[SUBPROCESS] {payload}")

        print("[DEBUG] Timeout waiting for ready signal")
        return False

    async def start_streaming(self) -> None:
        if not self._api_key:
            self.error_occurred.emit("DEEPGRAM_API_KEY not set")
            return

        self._running = True
        self._accumulated_transcript = ""
        self._chunks_received = 0
        self._chunks_sent = 0

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        self._output_queue = multiprocessing.Queue()
        self._input_queue = multiprocessing.Queue()

        worker_config = WorkerConfig(
            source_sample_rate=self._config.source_sample_rate,
            target_sample_rate=self._config.target_sample_rate,
            chunk_duration=self._config.chunk_duration,
        )

        self._process = multiprocessing.Process(
            target=run_capture_loop,
            args=(self._output_queue, self._input_queue, worker_config),
            daemon=True,
        )
        self._process.start()
        print(f"[DEBUG] Subprocess started with PID: {self._process.pid}")

        ready = await self._wait_for_ready()
        if not ready:
            self._stop_capture()
            self._running = False
            if self._output_queue is not None:
                self.error_occurred.emit("Failed to initialize audio capture")
            return

        url = self._build_url()
        headers = {"Authorization": f"Token {self._api_key}"}

        try:
            self._websocket = await websockets.connect(url, additional_headers=headers)
            print("[DEBUG] WebSocket connected to Deepgram")

            self._queue_reader_task = asyncio.create_task(self._queue_reader())
            sender_task = asyncio.create_task(self._sender(self._websocket))
            receiver_task = asyncio.create_task(self._receiver(self._websocket))

            await asyncio.gather(sender_task, receiver_task, self._queue_reader_task)

        except websockets.exceptions.InvalidStatus as e:
            error_msg = f"Connection failed: {e}"
            if hasattr(e, 'response') and e.response.status_code == 401:
                error_msg = "Invalid Deepgram API key"
            self.error_occurred.emit(error_msg)
        except Exception as e:
            self.error_occurred.emit(f"Streaming error: {e}")
        finally:
            self._stop_capture()
            self._running = False

    def _stop_capture(self) -> None:
        if self._input_queue is not None:
            try:
                self._input_queue.put_nowait(None)
            except Exception:
                pass

        if self._process is not None and self._process.is_alive():
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()

        self._process = None
        self._output_queue = None
        self._input_queue = None

    async def stop_streaming(self) -> None:
        self._running = False

        if self._queue_reader_task is not None:
            self._queue_reader_task.cancel()
            try:
                await self._queue_reader_task
            except asyncio.CancelledError:
                pass
            self._queue_reader_task = None

        self._stop_capture()

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None

    def get_transcript(self) -> str:
        return self._accumulated_transcript.strip()
