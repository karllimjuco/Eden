"""
main.py – Eden Voice Assistant event loop.

Pipeline:
  Porcupine ("Hey Eden") → faster-whisper (STT) → Ollama tool-calling → Piper TTS

Optimised for NVIDIA RTX 3050 (6 GB VRAM) + 8 GB system RAM.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

import requests

import config
from audio_io import listen_for_wake_word_then_record, pcm_to_wav_bytes, speak
from tools import TOOL_DEFINITIONS, TOOL_REGISTRY

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("eden")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are Eden, a concise and helpful offline Windows voice assistant.
Rules:
- Keep responses SHORT (1-3 sentences max) – they will be spoken aloud.
- For shutdown and restart commands: ALWAYS verbally confirm with the user
  before calling control_pc_power with action="shutdown" or "restart".
- Use the tools only when the user's intent clearly matches; otherwise answer directly.
- Never reveal internal tool mechanics or JSON to the user.
"""


# ---------------------------------------------------------------------------
# Whisper (faster-whisper)
# ---------------------------------------------------------------------------

def load_whisper():
    from faster_whisper import WhisperModel
    # Try CUDA first; fall back to CPU
    for device, compute in [("cuda", "float16"), ("cpu", "int8")]:
        try:
            model = WhisperModel(config.WHISPER_MODEL, device=device, compute_type=compute)
            log.info("Whisper loaded on %s (%s)", device, compute)
            return model
        except Exception as exc:
            log.warning("Whisper %s/%s failed: %s", device, compute, exc)
    raise RuntimeError("Could not load Whisper on any device.")


def transcribe(whisper_model, pcm: bytes) -> str:
    """Transcribe raw PCM bytes → text string."""
    import io, wave
    wav_bytes = pcm_to_wav_bytes(pcm)
    import tempfile, os
    # faster-whisper needs a file path or numpy array
    import numpy as np
    audio_arr = (
        np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    )
    segments, _ = whisper_model.transcribe(audio_arr, language="en", beam_size=5)
    text = " ".join(seg.text for seg in segments).strip()
    log.info("Transcribed: %r", text)
    return text


# ---------------------------------------------------------------------------
# Ollama chat with tool-calling
# ---------------------------------------------------------------------------

def ollama_chat_with_tools(user_text: str) -> str:
    """
    Send user_text to Ollama, handle tool calls, and return the final
    assistant text response.
    """
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_text},
    ]

    for _ in range(5):  # max tool-call rounds
        payload = {
            "model": config.OLLAMA_MODEL,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "stream": False,
            "options": config.OLLAMA_OPTIONS,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
        }

        try:
            resp = requests.post(
                f"{config.OLLAMA_BASE_URL}/api/chat",
                json=payload,
                timeout=60,
            )
            resp.raise_for_status()
        except requests.exceptions.ConnectionError:
            return "I can't reach Ollama. Is it running?"
        except Exception as exc:
            return f"LLM error: {exc}"

        data = resp.json()
        assistant_msg: dict = data.get("message", {})

        # Check for tool calls
        tool_calls: list[dict] = assistant_msg.get("tool_calls", [])
        if not tool_calls:
            # Final text response
            return assistant_msg.get("content", "").strip()

        # Execute each tool call
        messages.append({"role": "assistant", **assistant_msg})
        for tc in tool_calls:
            fn_name: str = tc["function"]["name"]
            fn_args: dict[str, Any] = tc["function"].get("arguments", {})

            log.info("Tool call: %s(%s)", fn_name, fn_args)
            fn = TOOL_REGISTRY.get(fn_name)
            if fn is None:
                tool_result = f"Unknown tool: {fn_name}"
            else:
                try:
                    tool_result = fn(**fn_args)
                except Exception as exc:
                    tool_result = f"Tool error: {exc}"

            log.info("Tool result: %s", tool_result)
            messages.append({
                "role": "tool",
                "name": fn_name,
                "content": str(tool_result),
            })

    return "I'm having trouble processing that request."


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("Loading Whisper model…")
    whisper_model = load_whisper()

    log.info("Eden is ready. Say 'Hey Eden' to start.")
    speak("Eden is online and ready.")

    while True:
        try:
            # 1. Wait for wake word, then record utterance
            pcm = listen_for_wake_word_then_record()
            if not pcm:
                log.info("No audio captured after wake word.")
                continue

            # 2. Transcribe
            speak("Mm-hmm?")  # brief acknowledgement
            user_text = transcribe(whisper_model, pcm)
            if not user_text:
                speak("I didn't catch that. Try again.")
                continue

            # 3. LLM + tool-calling
            response = ollama_chat_with_tools(user_text)
            log.info("Eden: %s", response)

            # 4. TTS playback
            speak(response)

        except KeyboardInterrupt:
            log.info("Shutting down Eden.")
            speak("Goodbye!")
            sys.exit(0)
        except Exception as exc:
            log.exception("Unexpected error in main loop: %s", exc)
            time.sleep(1)


if __name__ == "__main__":
    main()
