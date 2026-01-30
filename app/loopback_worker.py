from __future__ import annotations

import multiprocessing
from dataclasses import dataclass
from typing import Literal, Union

import numpy as np
# Monkey-patch for soundcard compatibility with numpy 2.x
if not hasattr(np, 'fromstring') or np.__version__.startswith('2'):
    np.fromstring = lambda s, dtype=None, count=-1, sep='': np.frombuffer(
        s if isinstance(s, bytes) else s.encode(), dtype=dtype, count=count
    )
from numpy.typing import NDArray
import soundcard as sc
from scipy.signal import resample


MessageType = Union[
    tuple[Literal["audio"], bytes],
    tuple[Literal["error"], str],
    tuple[Literal["ready"], None],
    tuple[Literal["debug"], str],
]


@dataclass(frozen=True)
class WorkerConfig:
    source_sample_rate: int = 48000
    target_sample_rate: int = 16000
    chunk_duration: float = 0.1


def _convert_to_mono(audio_data: NDArray[np.float64]) -> NDArray[np.float64]:
    if audio_data.ndim == 1:
        return audio_data
    return audio_data.mean(axis=1)


def _resample_audio(
    audio_data: NDArray[np.float64],
    source_frames: int,
    target_frames: int,
) -> NDArray[np.float64]:
    if source_frames == target_frames:
        return audio_data
    return resample(audio_data, target_frames)


def _convert_to_int16_bytes(audio_data: NDArray[np.float64]) -> bytes:
    clipped = np.clip(audio_data, -1.0, 1.0)
    int16_data = (clipped * 32767).astype(np.int16)
    return int16_data.tobytes()


def run_capture_loop(
    output_queue: multiprocessing.Queue[MessageType],
    input_queue: multiprocessing.Queue[str],
    config: WorkerConfig,
) -> None:
    output_queue.put(("debug", "Worker process started"))
    try:
        speaker = sc.default_speaker()
        if speaker is None:
            output_queue.put(("error", "No default speaker found"))
            return
        output_queue.put(("debug", f"Found speaker: {speaker.name}"))

        loopback = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        if loopback is None:
            output_queue.put(("error", f"No loopback device found for speaker: {speaker.name}"))
            return
        output_queue.put(("debug", f"Found loopback device: {loopback.name}"))

        frames_per_chunk = int(config.source_sample_rate * config.chunk_duration)
        target_frames = int(config.target_sample_rate * config.chunk_duration)

        with loopback.recorder(samplerate=config.source_sample_rate) as mic:
            output_queue.put(("debug", "Recorder context entered"))
            output_queue.put(("ready", None))
            output_queue.put(("debug", "Ready signal sent, starting in PAUSED state"))

            is_capturing = False
            chunk_count = 0

            while True:
                try:
                    signal = input_queue.get_nowait()
                    if signal == "stop":
                        output_queue.put(("debug", "Stop signal received, exiting"))
                        break
                    elif signal == "resume":
                        is_capturing = True
                        chunk_count = 0
                        output_queue.put(("debug", "Capture RESUMED"))
                    elif signal == "pause":
                        is_capturing = False
                        output_queue.put(("debug", "Capture PAUSED"))
                except Exception:
                    pass

                chunk = mic.record(numframes=frames_per_chunk)

                if is_capturing:
                    mono = _convert_to_mono(chunk)
                    chunk_count += 1

                    if chunk_count == 1 or chunk_count % 50 == 0:
                        rms = float(np.sqrt(np.mean(mono ** 2)))
                        output_queue.put(("debug", f"Chunk {chunk_count}: RMS={rms:.6f}"))

                    resampled = _resample_audio(mono, frames_per_chunk, target_frames)
                    audio_bytes = _convert_to_int16_bytes(resampled)
                    output_queue.put(("audio", audio_bytes))

    except Exception as e:
        output_queue.put(("error", f"Capture error: {e}"))
