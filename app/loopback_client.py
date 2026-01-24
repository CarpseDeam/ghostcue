from __future__ import annotations

import asyncio
import json
import multiprocessing
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional

import websockets
from websockets.protocol import State as WebSocketState
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from app.loopback_worker import MessageType, WorkerConfig, run_capture_loop


@dataclass(frozen=True)
class LoopbackConfig:
    source_sample_rate: int = 48000
    target_sample_rate: int = 16000
    channels: int = 1
    chunk_duration: float = 0.05
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
    silence_detected = pyqtSignal()

    def __init__(self, config: Optional[LoopbackConfig] = None) -> None:
        super().__init__()
        self._config = config or LoopbackConfig()
        self._api_key = os.getenv("DEEPGRAM_API_KEY", "")
        self._audio_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._process: Optional[multiprocessing.Process] = None
        self._output_queue: Optional[multiprocessing.Queue[MessageType]] = None
        self._input_queue: Optional[multiprocessing.Queue[str]] = None
        self._running = False
        self._accumulated_transcript = ""
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._queue_reader_task: Optional[asyncio.Task[None]] = None
        self._chunks_received = 0
        self._chunks_sent = 0
        self._is_warmed = False
        self._is_capturing = False
        self._sender_task: Optional[asyncio.Task[None]] = None
        self._receiver_task: Optional[asyncio.Task[None]] = None
        self._keepalive_task: Optional[asyncio.Task[None]] = None
        self._last_final_time: float = 0.0
        self._silence_timer: Optional[QTimer] = None
        self._silence_threshold_ms: int = 1000
        self._question_silence_threshold_ms: int = 500

    def set_silence_threshold(self, default_ms: int, question_ms: int = 500) -> None:
        self._silence_threshold_ms = default_ms
        self._question_silence_threshold_ms = question_ms
        print(f"[DEBUG] Silence thresholds set: default={default_ms}ms, question={question_ms}ms")

    def _start_silence_monitor(self) -> None:
        if self._silence_timer is None:
            self._silence_timer = QTimer()
            self._silence_timer.timeout.connect(self._check_silence)
        self._last_final_time = time.time()
        self._silence_timer.start(200)
        print("[DEBUG] Silence monitor started")

    def _stop_silence_monitor(self) -> None:
        if self._silence_timer is not None:
            self._silence_timer.stop()
            print("[DEBUG] Silence monitor stopped")

    def _check_silence(self) -> None:
        if not self._is_capturing:
            return

        transcript = self._accumulated_transcript.strip()
        if not transcript:
            return

        is_question = transcript.endswith('?')
        threshold = self._question_silence_threshold_ms if is_question else self._silence_threshold_ms

        elapsed_ms = (time.time() - self._last_final_time) * 1000
        if elapsed_ms >= threshold:
            q_indicator = " (question detected!)" if is_question else ""
            print(f"[DEBUG] Silence detected! {elapsed_ms:.0f}ms >= {threshold}ms threshold{q_indicator}")
            self._stop_silence_monitor()
            self.silence_detected.emit()

    async def warm_up(self) -> bool:
        if self._is_warmed:
            return True

        if not self._api_key:
            print("[DEBUG] Cannot warm up: DEEPGRAM_API_KEY not set")
            return False

        print("[DEBUG] Warming up loopback client...")

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
            self._terminate_process()
            return False

        url = self._build_url()
        headers = {"Authorization": f"Token {self._api_key}"}

        try:
            self._websocket = await websockets.connect(url, additional_headers=headers)
            print("[DEBUG] WebSocket connected to Deepgram (pre-warmed)")
        except Exception as e:
            print(f"[DEBUG] WebSocket connection failed during warm-up: {e}")
            self._terminate_process()
            return False

        self._running = True
        self._queue_reader_task = asyncio.create_task(self._queue_reader())
        self._sender_task = asyncio.create_task(self._sender(self._websocket))
        self._receiver_task = asyncio.create_task(self._receiver(self._websocket))

        self._is_warmed = True
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        print("[DEBUG] Loopback client warmed up and ready!")
        return True

    def _terminate_process(self) -> None:
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=1.0)
        self._process = None
        self._output_queue = None
        self._input_queue = None

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

    async def _ensure_websocket_connected(self) -> bool:
        ws_open = (self._websocket.state == WebSocketState.OPEN) if self._websocket is not None else None
        print(f"[DEBUG] _ensure_websocket_connected() called, websocket={self._websocket is not None}, open={ws_open}")
        if self._websocket is not None and self._websocket.state == WebSocketState.OPEN:
            return True

        print("[DEBUG] WebSocket stale or closed, reconnecting...")

        if self._websocket is not None:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None

        for task in [self._sender_task, self._receiver_task]:
            if task is not None:
                if not task.done():
                    task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception) as e:
                    print(f"[DEBUG] Task cleanup: {type(e).__name__}")

        self._sender_task = None
        self._receiver_task = None

        url = self._build_url()
        headers = {"Authorization": f"Token {self._api_key}"}

        try:
            self._websocket = await websockets.connect(url, additional_headers=headers)
            if self._websocket.state != WebSocketState.OPEN:
                print("[DEBUG] WebSocket connected but not in OPEN state")
                return False
            print("[DEBUG] WebSocket reconnected to Deepgram")
            self._sender_task = asyncio.create_task(self._sender(self._websocket))
            self._receiver_task = asyncio.create_task(self._receiver(self._websocket))
            return True
        except Exception as e:
            print(f"[DEBUG] WebSocket reconnection failed: {e}")
            self.error_occurred.emit(f"Failed to reconnect: {e}")
            return False

    async def _keepalive_loop(self) -> None:
        while self._running and self._is_warmed and not self._is_capturing:
            try:
                if self._websocket is not None and self._websocket.state == WebSocketState.OPEN:
                    await self._websocket.send(b'')
                    print("[DEBUG] Keepalive ping sent")
                await asyncio.sleep(15)
            except Exception as e:
                print(f"[DEBUG] Keepalive error: {e}")
                break

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
                                self._last_final_time = time.time()
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
        print(f"[DEBUG] start_streaming() called, is_warmed={self._is_warmed}")
        if not self._is_warmed:
            print("[DEBUG] Not warmed, falling back to cold start")
            await self._cold_start_streaming()
            return

        try:
            print("[DEBUG] About to call _ensure_websocket_connected()")
            connected = await self._ensure_websocket_connected()
            print(f"[DEBUG] _ensure_websocket_connected() returned {connected}")
            if not connected:
                print("[DEBUG] Could not establish WebSocket, falling back to cold start")
                self._is_warmed = False
                await self._cold_start_streaming()
                return
        except Exception as e:
            print(f"[DEBUG] Exception in _ensure_websocket_connected: {type(e).__name__}: {e}")
            self._is_warmed = False
            await self._cold_start_streaming()
            return

        if self._keepalive_task is not None:
            self._keepalive_task.cancel()
            self._keepalive_task = None
        print("[DEBUG] Starting capture (pre-warmed, instant)")
        self._accumulated_transcript = ""
        self._is_capturing = True
        self._chunks_received = 0
        self._chunks_sent = 0

        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        if self._input_queue is not None:
            self._input_queue.put("resume")
            print("[DEBUG] Resume signal sent to subprocess")
        self._start_silence_monitor()

    async def _cold_start_streaming(self) -> None:
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

        if self._input_queue is not None:
            self._input_queue.put("resume")

        url = self._build_url()
        headers = {"Authorization": f"Token {self._api_key}"}

        try:
            self._websocket = await websockets.connect(url, additional_headers=headers)
            print("[DEBUG] WebSocket connected to Deepgram")

            self._queue_reader_task = asyncio.create_task(self._queue_reader())
            self._sender_task = asyncio.create_task(self._sender(self._websocket))
            self._receiver_task = asyncio.create_task(self._receiver(self._websocket))
            self._start_silence_monitor()

            await asyncio.gather(self._sender_task, self._receiver_task, self._queue_reader_task)

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
                self._input_queue.put("stop")
            except Exception:
                pass
        self._terminate_process()

    async def stop_streaming(self) -> None:
        self._stop_silence_monitor()
        print("[DEBUG] Pausing capture")
        self._is_capturing = False

        if self._is_warmed and self._keepalive_task is None:
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

        if self._input_queue is not None:
            self._input_queue.put("pause")
            print("[DEBUG] Pause signal sent to subprocess")

    async def shutdown(self) -> None:
        self._stop_silence_monitor()
        print("[DEBUG] Shutting down loopback client")
        self._running = False
        self._is_warmed = False
        self._is_capturing = False

        for task in [self._queue_reader_task, self._sender_task, self._receiver_task, self._keepalive_task]:
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._queue_reader_task = None
        self._sender_task = None
        self._receiver_task = None
        self._keepalive_task = None

        if self._input_queue is not None:
            try:
                self._input_queue.put("stop")
            except Exception:
                pass

        self._terminate_process()

        if self._websocket:
            try:
                await self._websocket.close()
            except Exception:
                pass
            self._websocket = None

        print("[DEBUG] Loopback client shutdown complete")

    def get_transcript(self) -> str:
        return self._accumulated_transcript.strip()
