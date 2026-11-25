"""
config.py – Central configuration for Eden Voice Assistant.
Copy .env.example to .env and fill in your PICOVOICE_ACCESS_KEY.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
load_dotenv()

BASE_DIR = Path(__file__).parent.resolve()

# ---------------------------------------------------------------------------
# Picovoice / Wake-word
# ---------------------------------------------------------------------------
PICOVOICE_ACCESS_KEY: str = os.environ.get("PICOVOICE_ACCESS_KEY", "")
WAKE_WORD_MODEL_PATH: str = str(BASE_DIR / "hey_eden_windows.ppn")

# ---------------------------------------------------------------------------
# Whisper (faster-whisper)
# ---------------------------------------------------------------------------
WHISPER_MODEL: str = "base.en"          # small footprint, English-only
WHISPER_DEVICE: str = "cuda"            # falls back to "cpu" in main.py
WHISPER_COMPUTE_TYPE: str = "float16"   # GPU – use "int8" for CPU fallback

# ---------------------------------------------------------------------------
# Ollama / LLM
# ---------------------------------------------------------------------------
OLLAMA_MODEL: str = "qwen2.5:3b"
OLLAMA_BASE_URL: str = "http://localhost:11434"
OLLAMA_OPTIONS: dict = {
    "num_ctx": 2048,       # keep memory usage low on 8 GB RAM
}
OLLAMA_KEEP_ALIVE: str = "2m"          # unload model after 2 min of inactivity

# ---------------------------------------------------------------------------
# Piper TTS
# The Windows release zip extracts to piper/piper/piper.exe
# Voice models (.onnx + .onnx.json) are placed directly in piper/
# ---------------------------------------------------------------------------
PIPER_DIR: Path = BASE_DIR / "piper"
PIPER_EXE: Path = PIPER_DIR / "piper" / "piper.exe"   # nested after extraction
PIPER_VOICE_MODEL: Path = PIPER_DIR / "en_US-lessac-medium.onnx"

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
TEXT_ONLY_REPLY: bool = False   # Set True to skip TTS (text output only)

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
SAMPLE_RATE: int = 16_000           # Hz – required by Porcupine & Whisper
SILENCE_THRESHOLD: float = 500.0    # RMS below this = silence
SILENCE_DURATION_S: float = 1.5     # seconds of silence before VAD cutoff
MAX_RECORD_S: float = 30.0          # hard cap on a single utterance
