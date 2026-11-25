"""
tools.py – Modular Ollama tool functions for Eden Voice Assistant.

Each function maps to an Ollama tool definition and contains the actual
Python implementation that runs when the LLM calls it.
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Any

import pyperclip
import requests

import config

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool: PC Power Control
# ---------------------------------------------------------------------------

def control_pc_power(action: str, delay_seconds: int = 10) -> str:
    """
    Control PC power state.

    Parameters
    ----------
    action : str
        One of "shutdown", "restart", "sleep", "abort".
    delay_seconds : int
        Seconds before shutdown/restart executes (default 10, min 0).

    Returns a human-readable status string.
    """
    action = action.strip().lower()
    delay_seconds = max(0, int(delay_seconds))

    # Safety: shutdown and restart MUST NOT run without prior verbal confirmation.
    # The LLM is instructed (via system prompt in main.py) to always confirm
    # before calling this function with action="shutdown" or "restart".

    if action == "shutdown":
        cmd = ["shutdown", "/s", "/t", str(delay_seconds)]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            return f"Shutdown scheduled in {delay_seconds} seconds."
        return f"Shutdown failed: {result.stderr.decode(errors='replace')}"

    elif action == "restart":
        cmd = ["shutdown", "/r", "/t", str(delay_seconds)]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode == 0:
            return f"Restart scheduled in {delay_seconds} seconds."
        return f"Restart failed: {result.stderr.decode(errors='replace')}"

    elif action == "sleep":
        # rundll32 works without elevation
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "Putting the PC to sleep now."

    elif action == "abort":
        result = subprocess.run(["shutdown", "/a"], capture_output=True)
        if result.returncode == 0:
            return "Scheduled shutdown/restart has been cancelled."
        return "No pending shutdown to cancel (or cancellation failed)."

    else:
        return f"Unknown power action '{action}'. Use: shutdown, restart, sleep, abort."


# ---------------------------------------------------------------------------
# Tool: Launch Workspace
# ---------------------------------------------------------------------------

_WORKSPACE_APPS: dict[str, list[list[str]]] = {
    "coding": [
        ["code", "."],           # VS Code in current directory
    ],
    "study": [
        ["start", "", "chrome", "--new-window", "https://www.notion.so"],
    ],
    "gaming": [
        ["start", "", "steam://open/games"],
    ],
}


def launch_workspace(mode: str) -> str:
    """
    Launch a preset application workspace.

    Parameters
    ----------
    mode : str
        One of "coding", "study", "gaming".

    In gaming mode Ollama is immediately unloaded to free VRAM.
    """
    mode = mode.strip().lower()

    if mode not in _WORKSPACE_APPS:
        return f"Unknown workspace mode '{mode}'. Choose: coding, study, gaming."

    # Gaming mode: free VRAM by setting keep_alive=0 on current model
    if mode == "gaming":
        try:
            requests.post(
                f"{config.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": config.OLLAMA_MODEL,
                    "keep_alive": 0,
                    "prompt": "",
                },
                timeout=10,
            )
            log.info("Ollama model unloaded for gaming mode.")
        except Exception as exc:
            log.warning("Could not unload Ollama: %s", exc)

    # Launch each app in the preset
    launched = []
    for cmd in _WORKSPACE_APPS[mode]:
        try:
            subprocess.Popen(cmd, shell=(cmd[0] == "start"))
            launched.append(cmd[0])
        except FileNotFoundError:
            log.warning("Could not launch %s – not found in PATH.", cmd[0])

    apps = ", ".join(launched) if launched else "nothing (apps not found)"
    return f"Launched {mode} workspace: {apps}."


# ---------------------------------------------------------------------------
# Tool: Summarise Clipboard
# ---------------------------------------------------------------------------

def summarize_clipboard() -> str:
    """
    Read the current clipboard contents and return them for summarisation.
    The LLM will summarise the returned text.
    """
    try:
        text = pyperclip.paste()
    except Exception as exc:
        return f"Could not read clipboard: {exc}"

    if not text or not text.strip():
        return "The clipboard is empty."

    # Truncate to avoid flooding the context window
    if len(text) > 4000:
        text = text[:4000] + "\n… [truncated]"

    return f"Clipboard contents:\n\n{text}"


# ---------------------------------------------------------------------------
# Tool: Trigger n8n Webhook
# ---------------------------------------------------------------------------

def trigger_n8n_webhook(event_name: str, payload: dict[str, Any] | None = None) -> str:
    """
    POST to an n8n webhook endpoint.

    Parameters
    ----------
    event_name : str
        The webhook path segment (appended to N8N_WEBHOOK_BASE_URL in .env).
    payload : dict, optional
        JSON body to send.
    """
    import os
    base_url = os.environ.get("N8N_WEBHOOK_BASE_URL", "http://localhost:5678/webhook")
    url = f"{base_url}/{event_name}"

    try:
        resp = requests.post(url, json=payload or {}, timeout=10)
        resp.raise_for_status()
        return f"Webhook '{event_name}' triggered. Status: {resp.status_code}."
    except requests.exceptions.ConnectionError:
        return f"Could not reach n8n at {url}. Is n8n running?"
    except requests.exceptions.HTTPError as exc:
        return f"n8n webhook error: {exc}"
    except Exception as exc:
        return f"Webhook failed: {exc}"


# ---------------------------------------------------------------------------
# Ollama tool schemas (for /api/chat tools field)
# ---------------------------------------------------------------------------

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "control_pc_power",
            "description": (
                "Control the PC power state. IMPORTANT: Always ask the user "
                "to verbally confirm before executing 'shutdown' or 'restart'. "
                "Never call those without explicit confirmation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["shutdown", "restart", "sleep", "abort"],
                        "description": "Power action to perform.",
                    },
                    "delay_seconds": {
                        "type": "integer",
                        "description": "Seconds before shutdown/restart (default 10).",
                    },
                },
                "required": ["action"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "launch_workspace",
            "description": "Launch a preset application workspace on the PC.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["coding", "study", "gaming"],
                        "description": "Workspace preset to launch.",
                    },
                },
                "required": ["mode"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_clipboard",
            "description": "Read and summarise the current clipboard contents.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_n8n_webhook",
            "description": "Send an event to an n8n automation webhook.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_name": {
                        "type": "string",
                        "description": "The webhook path / event identifier.",
                    },
                    "payload": {
                        "type": "object",
                        "description": "Optional JSON payload to send with the event.",
                    },
                },
                "required": ["event_name"],
            },
        },
    },
]

# Dispatch table: tool name → Python callable
TOOL_REGISTRY: dict[str, Any] = {
    "control_pc_power": control_pc_power,
    "launch_workspace": launch_workspace,
    "summarize_clipboard": summarize_clipboard,
    "trigger_n8n_webhook": trigger_n8n_webhook,
}
