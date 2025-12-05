from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL_ALIAS = "gpt-5-mini"


class ModelId(str, Enum):
    """Provider-specific model identifiers."""

    OPENAI_GPT5_MINI = "openai/gpt-5-mini"
    OPENAI_GPT4_1_MINI = "openai/gpt-4.1-mini"
    GOOGLE_GEMINI_2_5_FLASH = "google/gemini-2.5-flash"
    XAI_GROK_4_1_FAST_REASONING = "xai/grok-4.1-fast-reasoning"
    DEEPSEEK = "deepseek/deepseek-v3.2-thinking"


DEFAULT_MODEL_ID = ModelId.OPENAI_GPT5_MINI.value

# Shorthand-to-provider model aliases for ergonomics
MODEL_ALIASES: dict[str, str] = {
    # GPT-5-mini
    "gpt-5-mini": ModelId.OPENAI_GPT5_MINI.value,
    "5-mini": ModelId.OPENAI_GPT5_MINI.value,
    "gpt5": ModelId.OPENAI_GPT5_MINI.value,
    "gpt5-mini": ModelId.OPENAI_GPT5_MINI.value,
    # GPT-4.1-mini
    "gpt-4.1-mini": ModelId.OPENAI_GPT4_1_MINI.value,
    "4.1-mini": ModelId.OPENAI_GPT4_1_MINI.value,
    "gpt4.1-mini": ModelId.OPENAI_GPT4_1_MINI.value,
    "gpt4-mini": ModelId.OPENAI_GPT4_1_MINI.value,
    # Gemini
    "gemini": ModelId.GOOGLE_GEMINI_2_5_FLASH.value,
    "google": ModelId.GOOGLE_GEMINI_2_5_FLASH.value,
    # Grok
    "grok": ModelId.XAI_GROK_4_1_FAST_REASONING.value,
    "xai": ModelId.XAI_GROK_4_1_FAST_REASONING.value,
    # DeepSeek v3.2 Reasoning
    "deepseek": ModelId.DEEPSEEK.value,
}

# Derive supported alias list (first alias per target) and allowed target IDs
_seen_targets: set[str] = set()
_primary_aliases: list[str] = []
_allowed_targets: set[str] = set()
for alias, target in MODEL_ALIASES.items():
    if target not in _seen_targets:
        _seen_targets.add(target)
        _primary_aliases.append(alias)
    _allowed_targets.add(target)
SUPPORTED_MODELS = tuple(_primary_aliases)
ALLOWED_MODEL_TARGETS = frozenset(_allowed_targets)


class OCRMode(str, Enum):
    """Supported OCR pipelines."""

    TESSERACT = "ocr-tesseract"
    EASYOCR = "ocr-easyocr"
    FUSION = "ocr-fusion"


class TextParseRequest(BaseModel):
    """Request payload for text parsing."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1)
    model: Optional[str] = Field(
        None,
        description="Model shorthand alias (e.g., gpt-5-mini, gemini).",
    )
    model_string: Optional[str] = Field(
        None, description="Exact provider model ID (takes precedence)."
    )
    source_type: str = Field(
        "text", description='Label for prompt conditioning (default: "text").'
    )


class TextParseResponse(BaseModel):
    """Response payload for text parsing."""

    model_config = ConfigDict(extra="forbid")

    event: dict[str, Any]


class ImageParseResponse(BaseModel):
    """Response payload for OCR parsing."""

    model_config = ConfigDict(extra="forbid")

    ocr_text: str
    event: dict[str, Any]


def resolve_model_choice(model: Optional[str], model_string: Optional[str]) -> str:
    """Return a provider model ID from either a shorthand alias or explicit string."""
    if model is not None and model_string is not None:
        raise ValueError("Specify either model or model_string, not both.")

    if model_string is not None:
        cleaned = model_string.strip()
        if not cleaned:
            raise ValueError("Model string cannot be empty.")
        return cleaned

    alias = (model or DEFAULT_MODEL_ALIAS).strip().lower()
    if alias in MODEL_ALIASES:
        return MODEL_ALIASES[alias]

    raise ValueError(
        f"Unsupported model '{model}'. Choose one of: {', '.join(SUPPORTED_MODELS)}."
    )

