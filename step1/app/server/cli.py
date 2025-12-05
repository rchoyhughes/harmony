#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Ensure the project root (step1) is on sys.path so "app" is importable when run from app/server
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.harmony_engine import HarmonyPipeline, Settings
from app.harmony_engine.core.models import DEFAULT_MODEL_ALIAS, OCRMode


QUOTE_CHARS = "'\"“”‘’"


def _sanitize_user_path(raw_path: str) -> Path:
    """Trim whitespace and surrounding quotes/smart quotes from user-supplied paths."""
    trimmed = raw_path.strip().strip(QUOTE_CHARS)
    if not trimmed:
        raise ValueError("No image path provided.")
    return Path(trimmed)


def _resolve_image_path(arg_path: Optional[Path], prompt_label: str) -> Path:
    """Resolve an optional CLI path argument or prompt interactively."""
    if arg_path is not None:
        return arg_path
    try:
        raw_path = input(prompt_label)
    except EOFError:
        raise ValueError("No image path provided.")
    return _sanitize_user_path(raw_path)


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Harmony Step 1 Server: text/image to structured event JSON."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    model_help = (
        "LLM model (shorthands) routed through your OpenAI-compatible endpoint. "
        "Shorthands: gpt-5-mini|gpt5|5-mini, gpt-4.1-mini|4.1-mini, "
        "gemini|google, grok|xai, deepseek. "
        f"Default model: {DEFAULT_MODEL_ALIAS}. "
        "Use --model-string for an exact provider ID."
    )
    model_string_help = (
        "Exact provider model ID (bypasses shorthands), e.g. openai/gpt-5-nano "
        "or deepseek/deepseek-chat. Use when your gateway exposes custom IDs."
    )

    text_parser = subparsers.add_parser(
        "text", help="Parse a raw text message into structured event JSON."
    )
    text_parser.add_argument(
        "message",
        nargs="*",
        help="The text snippet to parse (wrap in quotes to include spaces).",
    )
    text_model_group = text_parser.add_mutually_exclusive_group()
    text_model_group.add_argument(
        "--model",
        default=DEFAULT_MODEL_ALIAS,
        help=model_help,
    )
    text_model_group.add_argument(
        "--model-string",
        default=None,
        help=model_string_help,
    )

    for name, help_text in [
        ("ocr-tesseract", "Use Tesseract OCR to extract text from an image."),
        ("ocr-easyocr", "Use EasyOCR to extract text from an image."),
        ("ocr-fusion", "Run Tesseract and EasyOCR in parallel, then fuse the transcripts."),
    ]:
        parser_ocr = subparsers.add_parser(name, help=help_text)
        parser_ocr.add_argument(
            "image_path",
            nargs="?",
            type=Path,
            help="Path to the screenshot that contains the plan details. Prompts interactively if omitted.",
        )
        ocr_model_group = parser_ocr.add_mutually_exclusive_group()
        ocr_model_group.add_argument(
            "--model",
            default=DEFAULT_MODEL_ALIAS,
            help=model_help,
        )
        ocr_model_group.add_argument(
            "--model-string",
            default=None,
            help=model_string_help,
        )

    return parser


def _command_to_ocr_mode(command: str) -> OCRMode:
    mapping = {
        "ocr-tesseract": OCRMode.TESSERACT,
        "ocr-easyocr": OCRMode.EASYOCR,
        "ocr-fusion": OCRMode.FUSION,
    }
    if command not in mapping:
        raise ValueError(f"Unsupported OCR command: {command}")
    return mapping[command]


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_cli()
    args = parser.parse_args(argv)

    settings = Settings()  # type: ignore[call-arg]  # Pydantic BaseSettings accepts env/.env
    pipeline = HarmonyPipeline(settings)

    try:
        if args.command == "text":
            if args.message:
                message_text = " ".join(args.message)
            else:
                try:
                    message_text = input("Enter text to parse: ").strip()
                except EOFError:
                    raise ValueError("No text provided.")
                if not message_text:
                    raise ValueError("Cannot parse an empty text snippet.")

            event = pipeline.parse_text(
                text=message_text,
                model=args.model,
                model_string=args.model_string,
                source_type="text",
            )
            result: dict[str, object] = {"event": event}
        else:
            prompt_map = {
                "ocr-tesseract": "Enter path to screenshot image (Tesseract): ",
                "ocr-easyocr": "Enter path to screenshot image (EasyOCR): ",
                "ocr-fusion": "Enter path to screenshot image (Fusion OCR): ",
            }
            image_path_arg = _resolve_image_path(
                args.image_path,
                prompt_map[args.command],
            )
            expanded_path = Path(image_path_arg).expanduser().resolve()
            if not expanded_path.exists():
                raise FileNotFoundError(f"Image not found: {expanded_path}")

            image_bytes = expanded_path.read_bytes()
            ocr_mode = _command_to_ocr_mode(args.command)
            result = pipeline.parse_image(
                image_bytes=image_bytes,
                ocr_mode=ocr_mode,
                model=args.model,
                model_string=args.model_string,
            )

        print(json.dumps(result, indent=2))
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

