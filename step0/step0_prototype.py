#!/usr/bin/env python3
"""
Harmony Phase 0 prototype.

Capabilities:
1. Accept a raw text snippet (ex: an iMessage) and ask OpenAI's GPT-4.1-mini
   model to turn it into structured, calendar-ready JSON.
2. Accept a screenshot, extract its text with OCR, and run the same parsing
   pipeline on the extracted text.

Usage:
    python step0_prototype.py text "Tim: Wanna do dinner at 7 next Tuesday?"
    python step0_prototype.py image /path/to/imessage_screenshot.png

Prereqs:
    - Install dependencies: pip install -r requirements.txt
    - Create a .env file with OPENAI_API_KEY=...
    - Install Tesseract OCR (macOS: brew install tesseract) so pytesseract
      can find the CLI binary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Iterable, Optional

from datetime import datetime
from dotenv import load_dotenv  # type: ignore[import]
from openai import OpenAI  # type: ignore[import]
from PIL import Image  # type: ignore[import]
import pytesseract  # type: ignore[import]
import zoneinfo

TIMEZONE = "America/New_York"
today = datetime.now(zoneinfo.ZoneInfo(TIMEZONE)).date().isoformat()

SYSTEM_PROMPT = dedent(
    """
    You are Harmony, a gentle, privacy-minded assistant that turns messy plans
    into tentative calendar suggestions. You must ALWAYS reply with a single
    JSON object that matches this structure:
    {
      "event_title": string | null,
      "event_window": {
        "start": {
          "datetime_text": string,
          "calendar_iso": string | null,
          "timezone": string | null,
          "certainty": "low" | "medium" | "high"
        },
        "end": {
          "datetime_text": string | null,
          "calendar_iso": string | null,
          "timezone": string | null,
          "certainty": "low" | "medium" | "high"
        } | null
      },
      "location": string | null,
      "participants": [string],  // may be empty if there are no clear participants
      "source_text": string,
      "notes": string | null,
      "confidence": number between 0 and 1,
      "follow_up_actions": [
        {
          "action": string,
          "reason": string
        }
      ],
      "context": {
        "today": string,
        "assumed_timezone": string
      }
    }

    Guidelines:
    - Mirror fuzzy phrasing (“next Tuesday”, “around 7”) in datetime_text.
    - Only populate calendar_iso when you feel precise enough to bet on it.
    - If you cannot find a real event, set event_title to null and explain why
      inside follow_up_actions.
    - Participants should be humans referenced or implied in the text.
    - Confidence reflects how certain you feel about the entire suggestion.
    - Keep the tone neutral and actionable.
    - follow_up_actions should be an array (possibly empty), never null.
    - Echo back the provided "today" and timezone inside the `context` object.
    """
).strip()


class HarmonyStepZero:
    """Minimal intake pipeline for Harmony's Phase 0 prototype."""

    def __init__(self, model: str = "gpt-4.1-mini") -> None:
        # Load .env from project root (one level up from step0/)
        project_root = Path(__file__).parent.parent
        env_path = project_root / ".env"
        load_dotenv(dotenv_path=env_path)
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is missing. Put it inside .env (see README)."
            )
        self.client = OpenAI(api_key=self.api_key)
        self.model = model

    def run_text_pipeline(self, text: str) -> Dict[str, Any]:
        """Send raw text to the LLM and return structured event JSON."""
        if not text or not text.strip():
            raise ValueError("Cannot parse an empty text snippet.")

        payload = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": dedent(
                            f"""
                            Source message:
                            \"\"\"{text.strip()}\"\"\"

                            Today's date: {today}
                            Assume the user is in the timezone: {TIMEZONE}.

                            Please respond with the JSON object now, following the JSON structure exactly.
                            """
                        ).strip(),
                    }
                ],
            },
        ]

        response = self.client.responses.create(
            model=self.model,
            input=payload,
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        return self._response_to_json(response)

    def run_image_pipeline(self, image_path: Path) -> Dict[str, Any]:
        """
        Extract text from an image (screenshot, photo, etc.) and run the
        structured parsing pipeline.
        """
        ocr_text = self.extract_text_from_image(image_path)
        structured_event = self.run_text_pipeline(ocr_text)

        print("🔍 OCR text:", file=sys.stderr)
        print(ocr_text, file=sys.stderr)

        return {
            "ocr_text": ocr_text,
            "event": structured_event,
        }

    @staticmethod
    def extract_text_from_image(image_path: Path) -> str:
        """Use pytesseract to grab text from the provided screenshot."""
        expanded_path = Path(image_path).expanduser().resolve()
        if not expanded_path.exists():
            raise FileNotFoundError(f"Image not found: {expanded_path}")

        try:
            with Image.open(expanded_path) as img:
                raw_text = pytesseract.image_to_string(img)
        except pytesseract.TesseractNotFoundError as exc:
            raise RuntimeError(
                "Tesseract is not installed. Install it (e.g., `brew install tesseract`)"
                " or set the TESSERACT_CMD environment variable to its binary."
            ) from exc

        cleaned = "\n".join(
            line.strip() for line in raw_text.splitlines() if line.strip()
        )
        if not cleaned:
            raise RuntimeError(
                "OCR succeeded but returned empty text. Try a clearer screenshot."
            )

        return cleaned

    @staticmethod
    def _response_to_json(response: Any) -> Dict[str, Any]:
        """Normalize OpenAI Responses output (or Chat Completions fallback) to JSON."""
        raw_text = HarmonyStepZero._extract_output_text(response)
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Model output was not valid JSON:\n{raw_text}"
            ) from exc

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        """
        Robustly pull the first text block out of a Responses or ChatCompletion
        response, so we can parse it as JSON.
        """
        output = getattr(response, "output", None)
        if output:
            text_chunks = []
            for item in output:
                item_type = getattr(item, "type", None) or item.get("type")
                if item_type != "output_text":
                    continue
                content = getattr(item, "content", None) or item.get("content", [])
                for chunk in content:
                    chunk_type = getattr(chunk, "type", None) or chunk.get("type")
                    if chunk_type != "text":
                        continue
                    chunk_text = getattr(chunk, "text", None) or chunk.get("text", {})
                    value = getattr(chunk_text, "value", None) or chunk_text.get("value")
                    if value:
                        text_chunks.append(value)
            if text_chunks:
                return "".join(text_chunks)

        # Fallback: chat.completions compatibility
        choices = getattr(response, "choices", None)
        if choices:
            first_choice = choices[0]
            message = getattr(first_choice, "message", None) or first_choice.get(
                "message"
            )
            if message:
                content = getattr(message, "content", None) or message.get("content")
                if isinstance(content, str):
                    return content
                if isinstance(content, Iterable):
                    chunks: list[str] = []
                    for part in content:
                        if not part:
                            continue
                        if isinstance(part, str):
                            chunks.append(part)
                            continue
                        text_attr = getattr(part, "text", None)
                        if text_attr:
                            chunks.append(text_attr)
                            continue
                        if isinstance(part, dict):
                            chunks.append(part.get("text", ""))
                    if chunks:
                        return "".join(chunks)
        raise RuntimeError("Could not find text in the model response.")


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Harmony Step 0: text/image to structured event JSON."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    text_parser = subparsers.add_parser(
        "text", help="Parse a raw text message into structured event JSON."
    )
    text_parser.add_argument(
        "message",
        nargs="*",
        help="The text snippet to parse (wrap in quotes to include spaces).",
    )
    text_parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="Override the OpenAI model (default: gpt-4.1-mini).",
    )

    image_parser = subparsers.add_parser(
        "image", help="Run OCR on a screenshot, then parse the extracted text."
    )
    image_parser.add_argument(
        "image_path",
        nargs="?",
        type=Path,
        help="Path to the screenshot that contains the plan details. If omitted, you will be prompted interactively.",
    )
    image_parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="Override the OpenAI model (default: gpt-4.1-mini).",
    )

    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_cli()
    args = parser.parse_args(argv)
    message_text: Optional[str] = None
    image_path_arg: Optional[Path] = None
    if args.command == "text":
        if args.message:
            # user passed the message on the command line
            message_text = " ".join(args.message)
        else:
            # interactive mode
            try:
                message_text = input("Enter text to parse: ").strip()
            except EOFError:
                raise ValueError("No text provided.")
            if not message_text:
                raise ValueError("Cannot parse an empty text snippet.")
    elif args.command == "image":
        if args.image_path is not None:
            image_path_arg = args.image_path
        else:
            # Interactive mode for image path
            try:
                raw_path = input("Enter path to screenshot image: ").strip()
            except EOFError:
                raise ValueError("No image path provided.")
            if not raw_path:
                raise ValueError("No image path provided.")
            image_path_arg = Path(raw_path)

    try:
        harmony = HarmonyStepZero(model=args.model)
        if message_text is not None:
            result = harmony.run_text_pipeline(message_text)
        else:
            assert image_path_arg is not None
            result = harmony.run_image_pipeline(image_path_arg)
        print("✅ Parsed result:")
        print(json.dumps(result, indent=2))
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
