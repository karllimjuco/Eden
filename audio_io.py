"""
audio_io.py – Microphone listener, VAD-based recording, and Piper TTS playback.

Flow:
  1. Continuous mic stream fed to Porcupine for wake-word detection.
  2. On "Hey Eden" detection → record until energy drops below threshold
     (or MAX_RECORD_S is reached) → return raw PCM bytes.
  3. speak(text) → pipe text into Piper, play resulting WAV, then resume mic.
"""

from __future__ import annotations

import io
import logging
import queue
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Optional

import numpy as np
import pvporcupine
import sounddevice as sd

import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared mute flag – prevents mic processing while Eden is speaking
# ---------------------------------------------------------------------------
_speaking = threading.Event()


# ---------------------------------------------------------------------------
# Porcupine helper
# ---------------------------------------------------------------------------

def create_porcupine(keyword_path: str) -> pvporcupine.Porcupine:
    """Initialise Porcupine with the .ppn wake-word model."""
    ppn = pvporcupine.create(
        access_key=config.PICOVOICE_ACCESS_KEY,
        keyword_paths=[keyword_path],
        sensitivities=[0.6],
    )
    return ppn


# ---------------------------------------------------------------------------
# Energy / silence helpers
# ---------------------------------------------------------------------------

def _rms(frame: np.ndarray) -> float:
    return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))


# ---------------------------------------------------------------------------
# Main listener loop
# ---------------------------------------------------------------------------

def listen_for_wake_word_then_record(
    keyword_path: str = config.WAKE_WORD_MODEL_PATH,
) -> Optional[bytes]:
    """
    Block until "Hey Eden" is detected, then record and return PCM audio
    (16-bit signed, mono, 16 kHz) as raw bytes.

    Returns None if the user says nothing within MAX_RECORD_S seconds.
    """
    porcupine = create_porcupine(keyword_path)
    frame_len = porcupine.frame_length  # e.g. 512 samples
    sr = config.SAMPLE_RATE
    detected = threading.Event()
    audio_q: queue.Queue[np.ndarray] = queue.Queue()

    def _callback(indata: np.ndarray, frames: int, time_info, status):
        if status:
            log.debug("sounddevice status: %s", status)
        # Skip while Eden is speaking to avoid hearing herself
        if _speaking.is_set():
            return
        audio_q.put(indata.copy())

    with sd.InputStream(
        samplerate=sr,
        channels=1,
        dtype="int16",
        blocksize=frame_len,
        callback=_callback,
    ):
        log.info("Listening for 'Hey Eden'…")

        # --- Phase 1: Wake-word detection ---
        buffer = np.array([], dtype=np.int16)
        while not detected.is_set():
            chunk = audio_q.get()
            flat = chunk.flatten()
            buffer = np.concatenate([buffer, flat])
            while len(buffer) >= frame_len:
                frame = buffer[:frame_len]
                buffer = buffer[frame_len:]
                result = porcupine.process(frame)
                if result >= 0:
                    log.info("Wake word detected!")
                    detected.set()
                    break

        # --- Phase 2: Utterance recording ---
        log.info("Recording utterance…")
        recorded: list[np.ndarray] = []
        silence_start: Optional[float] = None
        deadline = time.monotonic() + config.MAX_RECORD_S

        while time.monotonic() < deadline:
            try:
                chunk = audio_q.get(timeout=0.05)
            except queue.Empty:
                continue
            flat = chunk.flatten()
            recorded.append(flat)

            if _rms(flat) < config.SILENCE_THRESHOLD:
                if silence_start is None:
                    silence_start = time.monotonic()
                elif time.monotonic() - silence_start >= config.SILENCE_DURATION_S:
                    log.info("Silence detected – stopping recording.")
                    break
            else:
                silence_start = None  # reset on speech energy

    porcupine.delete()

    if not recorded:
        return None

    pcm = np.concatenate(recorded).astype(np.int16).tobytes()
    return pcm


def pcm_to_wav_bytes(pcm: bytes, sample_rate: int = config.SAMPLE_RATE) -> bytes:
    """Wrap raw 16-bit mono PCM in a WAV container (in-memory)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Piper TTS playback
# ---------------------------------------------------------------------------

def speak(text: str) -> None:
    """
    Synthesise *text* with Piper and play the result through the default
    audio output.  Pauses mic capture while speaking.
    """
    if config.TEXT_ONLY_REPLY:
        print(f"[Eden]: {text}")
        return

    if not config.PIPER_EXE.exists():
        log.error("Piper executable not found at %s", config.PIPER_EXE)
        print(f"[Eden TTS unavailable]: {text}")
        return

    _speaking.set()
    try:
        cmd = [
            str(config.PIPER_EXE),
            "--model", str(config.PIPER_VOICE_MODEL),
            "--output_raw",
        ]
        proc = subprocess.run(
            cmd,
            input=text.encode("utf-8"),
            capture_output=True,
        )
        if proc.returncode != 0:
            log.error("Piper error: %s", proc.stderr.decode(errors="replace"))
            return

        raw_audio = proc.stdout  # 16-bit signed, 22050 Hz mono (lessac-medium)
        audio_arr = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32) / 32768.0

        # Play and block until done
        sd.play(audio_arr, samplerate=22050)
        sd.wait()
    finally:
        _speaking.clear()
