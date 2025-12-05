from __future__ import annotations

from pathlib import Path

PROMPT_PATH = Path(__file__).with_name("system_prompt.md")


def load_system_prompt() -> str:
    """Load the system prompt from the colocated markdown file."""
    try:
        return PROMPT_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"System prompt file not found at {PROMPT_PATH}. Ensure it exists."
        ) from exc


SYSTEM_PROMPT = load_system_prompt()

