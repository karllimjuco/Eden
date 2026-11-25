# Eden

A lightweight, 100% offline Windows voice assistant triggered by **"Hey Eden"**, optimized for an NVIDIA RTX 3050 (6GB VRAM) and 8GB system RAM.

## Pipeline

`Porcupine ("Hey Eden")` → `faster-whisper (base.en)` → `Ollama (qwen2.5:3b)` → `Piper TTS (en_US-lessac-medium)`

## Project Structure

- `config.py` — Environment loading, model/context settings (`num_ctx=2048`, `keep_alive="2m"`), Piper paths, and `TEXT_ONLY_REPLY` toggle.
- `audio_io.py` — Continuous Porcupine wake-word listener, energy/silence-based VAD cutoff, and Piper TTS playback.
- `tools.py` — Modular Ollama tools:
  - `control_pc_power` (`shutdown`, `restart`, `sleep`, `abort`)
  - `launch_workspace` (`coding`, `study`, `gaming` — unloads Ollama with `keep_alive=0` in gaming mode)
  - `summarize_clipboard`
  - `trigger_n8n_webhook`
- `main.py` — Main event loop with CUDA `float16` Whisper (CPU `int8` fallback) and Ollama tool-calling.
- `setup_startup.ps1` — Registers a Windows Task Scheduler job to launch `.venv\Scripts\pythonw.exe main.py` silently 15 seconds after logon.

## Setup

1. **Create & activate virtual environment, install dependencies:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -r requirements.txt
   ```
2. **Download Piper TTS & voice model into `./piper/`:**
   - Extract `piper_windows_amd64.zip` from [rhasspy/piper](https://github.com/rhasspy/piper/releases/latest) into `piper/`.
   - Download `en_US-lessac-medium.onnx` and `en_US-lessac-medium.onnx.json` into `piper/`.
3. **Configure Ollama (with 6GB VRAM / 8GB RAM optimizations):**
   - Set user env vars: `OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_KEEP_ALIVE=2m`.
   - Pull model: `ollama pull qwen2.5:3b`.
4. **Configure keys & wake word:**
   - Copy `.env.example` to `.env` and add your `PICOVOICE_ACCESS_KEY`.
   - Place your trained `hey_eden_windows.ppn` in the project root.
5. **Run:**
   ```powershell
   .\.venv\Scripts\python.exe main.py
   ```
