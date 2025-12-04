#!/usr/bin/env python3
"""
Harmony Phase 0 prototype.

Capabilities:
1. Accept a raw text snippet (ex: an iMessage) and ask a Vercel AI Gateway
   model (default: gpt-5-mini) to turn it into structured, calendar-ready JSON.
2. Accept a screenshot, extract its text with OCR, and run the same parsing
   pipeline on the extracted text.

Usage:
    python step0_prototype.py text "Tim: Wanna do dinner at 7 next Tuesday?"
    python step0_prototype.py ocr-tesseract /path/to/imessage_screenshot.png
    python step0_prototype.py ocr-easyocr /path/to/imessage_screenshot.png
    python step0_prototype.py ocr-fusion /path/to/imessage_screenshot.png

Prereqs:
    - Install dependencies: pip install -r requirements.txt
    - Create a .env file with:
        VERCEL_AI_GATEWAY_API_KEY=...
      (Use your Vercel AI Gateway key.)
    - Install Tesseract OCR (macOS: brew install tesseract) so pytesseract
      can find the CLI binary.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Iterable, Optional, Union

# Optional EasyOCR support
try:
    import easyocr  # type: ignore
    EASYOCR_AVAILABLE = True
except Exception:
    EASYOCR_AVAILABLE = False

from datetime import datetime
from dotenv import load_dotenv  # type: ignore[import]
from openai import OpenAI  # type: ignore[import]
from PIL import Image  # type: ignore[import]
import pytesseract  # type: ignore[import]
import zoneinfo

TIMEZONE = "America/New_York"
DEFAULT_GATEWAY_URL = "https://ai-gateway.vercel.sh/v1"


class ModelId(str, Enum):
    """Provider-specific model identifiers."""

    OPENAI_GPT5_MINI = "openai/gpt-5-mini"
    OPENAI_GPT4_1_MINI = "openai/gpt-4.1-mini"
    GOOGLE_GEMINI_2_5_FLASH = "google/gemini-2.5-flash"
    XAI_GROK_4_1_FAST_REASONING = "xai/grok-4.1-fast-reasoning"
    DEEPSEEK = "deepseek/deepseek-v3.2-thinking"


DEFAULT_MODEL = ModelId.OPENAI_GPT5_MINI.value
# SUPPORT_MODELS will be derived after MODEL_ALIASES is defined.
SUPPORTED_MODELS: tuple[str, ...] = ()
today = datetime.now(zoneinfo.ZoneInfo(TIMEZONE)).date().isoformat()

# Shorthand-to-provider model aliases for CLI ergonomics
MODEL_ALIASES: Dict[str, str] = {
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

SYSTEM_PROMPT = dedent(
    """
    You are Harmony, a gentle, privacy-minded assistant that turns messy plans
    into tentative calendar suggestions. You must ALWAYS reply with a single
    JSON object that matches this structure exactly (no extra keys, no extra text):

    {
      "event_title": string | null,
      "event_window": {
        "start": {
          "date_iso": string | null,
          "time_iso": string | null,
          "time_text": string | null,
          "datetime_text": string,
          "timezone": string | null,
          "certainty": "low" | "medium" | "high"
        },
        "end": {
          "date_iso": string | null,
          "time_iso": string | null,
          "time_text": string | null,
          "datetime_text": string | null,
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

    General rules:
    - Always return VALID JSON that matches this schema and nothing else.
    - Use the provided "today" and "assumed_timezone" when interpreting relative dates.
    - Mirror fuzzy phrasing (“next Tuesday”, “around 7”, “this weekend”) in datetime_text.
    - Confidence reflects how certain you feel about the entire suggestion.

    Input source rules:
    - The user message will always begin with "Source type: <value>" where the
      value is one of: "text", "ocr-tesseract", "ocr-easyocr", or "ocr-fusion".
    - "text" means the content was provided directly by the user as plain text.
    - "ocr-tesseract" or "ocr-easyocr" means the text was extracted from a
      screenshot via the specified OCR engine.
    - "ocr-fusion" means you will receive BOTH OCR transcripts, delineated with
      headers such as "[Tesseract OCR]" and "[EasyOCR OCR]".
    - Tesseract strengths: reliable on crisp, high-contrast screenshots and
      structured chat logs, but it may miss stylized fonts, emojis, or low-light
      captures.
    - EasyOCR strengths: handles stylized fonts, low-light photos, and mixed
      languages better, but may hallucinate punctuation, spacing, or duplicate
      lines.
    - When Source type is "ocr-fusion", synthesize the most trustworthy details
      from BOTH transcripts—prefer agreement, and use model strengths to decide
      which snippet is more reliable.
    - For any OCR-based source, treat chat metadata (timestamps, delivery labels,
      etc.) as UI artifacts unless the conversational text explicitly mentions
      them as part of the plan.

    Event title rules:
    - The event title must be short, neutral, and calendar-friendly.
    - Avoid long descriptive phrases or full-sentence summaries.
    - If the plan is casual or home-based (e.g., "come over and hang out", "making sandwiches and chilling", "putting up Christmas"), create a concise title such as:
      - "Hang out at Victor's"
      - "Visit Victor's place"
      - "Christmas decorating at Victor's"
    - Do NOT include incidental details (like food prep or side activities) unless they define the purpose of the event (e.g. "Dinner with Tim").
    - If the location is implied to be someone’s home, titles may reflect that (e.g., "Hangout at Victor's").
    - If no clear purpose is stated, use a generic format such as "Hangout with <names>".

    Date/time rules:
    - If the text provides a clear date AND time (including relative forms like
      "tomorrow at 7", "Friday at 6pm"), set date_iso to the resolved date
      (e.g. "2025-12-05"), set time_iso to the resolved time in 24-hour format
      (e.g. "19:00:00"), and set certainty to "high". Keep the original human
      phrasing in datetime_text.
    - If the date is clear but NO specific clock time is given, DO NOT invent a
      time. Set date_iso to the resolved date, set time_iso to null, and put a
      short explanation in time_text (e.g. "time not specified" or "evening").
      Keep the human phrasing in datetime_text (e.g. "December 5 (time not
      specified)"), set certainty to "medium", and add a follow_up_action to
      confirm the exact time.
    - If only vague time-of-day words are present ("morning", "evening",
      "night", "after work") without a clear date, set both date_iso and
      time_iso to null, keep those words in time_text and datetime_text, and set
      certainty to "low" or "medium". Never guess a specific clock time from
      vague phrases alone.
    - If a time refers to someone's availability (e.g. "if I can leave by 6:30",
      "I'm free after 4", "I can do anytime before 3"), DO NOT treat that as
      the event start time. Treat it as a constraint that can be mentioned in
      notes, time_text, or follow_up_actions, but leave time_iso null unless
      there is a clear event start time.
    - Ignore UI timestamps (such as chat app metadata like "Sunday 4:32PM", message
      timestamps, or delivery indicators) unless the conversational text explicitly
      refers to them as part of the plan (e.g. "let's meet at 4:32PM Sunday"). When
      Source type is "ocr", treat any standalone day+time line as UI metadata and
      do NOT use it for date_iso or time_iso. When in doubt, leave time_iso null
      and mention the timestamp only in notes if needed.

    Event existence:
    - If you cannot find a coherent, real plan or event, set event_title to null,
      leave date_iso and time_iso as null for both start and end, and explain why
      inside follow_up_actions. Still echo back the source_text and fill context.

    Participants:
    - "participants" should list specific humans who are reasonably likely to
      attend the event (e.g. "Tim", "Dad", "Therapist").
    - When a concrete plan or event is discussed in a conversation and specific
      people are named in connection with that plan (for example, their name
      appears near messages about going, attending, being free, or reacting to
      the plan), include those named people in participants unless they
      explicitly decline.
    - Names that appear in a chat header, sender labels, or near the plan
      still count as associated with the conversation and may be participants.
    - If someone is directly invited (e.g. "if you wanna come", "do you wanna go",
      "you should come") and they have NOT explicitly declined, you should treat
      them as a likely participant and include their name in participants.
    - If a person clearly expresses interest or tentative agreement (e.g.
      "I think I'm free", "that looks cool", "I'm down"), treat them as a likely
      participant as well.
    - You do NOT know which person is the app "user" or who said which line.
      Treat all named humans associated with the plan symmetrically and do not
      try to infer roles like "inviter" or "invitee".
    - If there is exactly one specific human name in the conversation and a
      real event is clearly being planned or considered, you MUST include that
      name in participants unless they have clearly declined.
    - When in doubt between including or excluding a named human as a
      participant, prefer to INCLUDE them as a participant rather than leaving
      the array empty.
    - Do NOT include generic groups such as "friends", "coworkers", "people"
      in participants. Instead, mention them in notes (e.g. "with some friends").
    - If someone explicitly says they cannot attend (e.g. "I can't make it",
      "I won't be there"), do NOT include them in participants, but you may
      describe that fact in notes.
    - Participants may be an empty array only if there are truly no clear
      attendees (for example, brainstorming possibilities without any agreement
      or named people only mentioned in a completely unrelated context).

    Notes and follow-up actions:
    - Use notes for short, neutral summaries or important context (e.g.
      "Invitation to a concert on December 5; time not specified.").
    - You do NOT know which participant is the app "user" or who is speaking.
      Avoid first- or second-person language such as "I", "me", "we",
      "you", or "user" in notes or follow_up_actions. Also avoid role words
      like "sender", "recipient", or "poster". Refer to people by
      name or as "participants" or "the conversation" instead.
    - When invitations or plans are mentioned, do NOT state or imply who invited
      whom or who the invitation is directed to. Do not use phrases like
      "X invited Y" or "an invitation was extended to Tim" or "the poster" or
      "the recipient". Instead, describe the situation in fully neutral terms,
      such as "the conversation discusses going to the event together" or
      "there is an invitation to attend the event involving the named
      participants".
    - follow_up_actions should be an array (possibly empty), never null.
      Each action should be a small, concrete next step (e.g. "Confirm the
      exact start time", "Check if the invitee is still free that evening").
    - Do NOT fabricate unknown details. Instead, propose follow-up actions to
      clarify them (e.g. confirm missing date, time, or location, or look up
      public event details).

    Context:
    - Echo back the provided "today" and "assumed_timezone" inside the
      context object without changing them.
    """
).strip()


class HarmonyStepZero:
    """Minimal intake pipeline for Harmony's Phase 0 prototype."""

    def __init__(
        self,
        model: Union[str, ModelId] = DEFAULT_MODEL,
        allow_unknown_model: bool = False,
    ) -> None:
        # Load .env from project root (one level up from step0/)
        project_root = Path(__file__).parent.parent
        env_path = project_root / ".env"
        load_dotenv(dotenv_path=env_path)
        gateway_url = os.getenv("VERCEL_AI_GATEWAY_URL", DEFAULT_GATEWAY_URL)
        gateway_api_key = os.getenv("VERCEL_AI_GATEWAY_API_KEY")
        if not gateway_api_key:
            raise RuntimeError(
                "VERCEL_AI_GATEWAY_API_KEY is missing. Put it inside .env (see STEP0_USAGE.md)."
            )
        self.client = OpenAI(
            api_key=gateway_api_key,
            base_url=gateway_url.rstrip("/"),
        )
        self.model = self._validate_model(model, allow_unknown=allow_unknown_model)

    @staticmethod
    def _validate_model(
        model: Union[str, ModelId], allow_unknown: bool = False
    ) -> str:
        """Ensure the selected model is one of the supported gateway options."""
        if isinstance(model, ModelId):
            model_value = model.value
        else:
            # At this point, --model has already been parsed to a provider ID by _parse_model_arg,
            # and --model-string is passed through as-is. Avoid double-parsing.
            model_value = str(model).strip()
        if model_value not in ALLOWED_MODEL_TARGETS and not allow_unknown:
            raise ValueError(
                f"Unsupported model '{model_value}'. Choose one of: {', '.join(SUPPORTED_MODELS)}."
            )
        return model_value

    def run_text_pipeline(self, text: str, source_type: str = "text") -> Dict[str, Any]:
        """Send raw text to the LLM and return structured event JSON.

        source_type is either "text" (direct user text) or "ocr" (text extracted
        from an image screenshot).
        """
        if not text or not text.strip():
            raise ValueError("Cannot parse an empty text snippet.")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Source type: {source_type}

                    Source message:
                    \"\"\"{text.strip()}\"\"\"

                    Today's date: {today}
                    Assume the user is in the timezone: {TIMEZONE}.

                    Please respond with the JSON object now, following the JSON structure exactly.
                    """
                ).strip(),
            },
        ]

        chat_api: Any = getattr(self.client, "chat", None)
        if chat_api is None:
            raise RuntimeError("LLM client is missing the chat API surface.")
        completions_api: Any = getattr(chat_api, "completions", None)
        if completions_api is None:
            raise RuntimeError("LLM client is missing the chat.completions API.")

        resp_create: Any = completions_api.create  # pyright: ignore[reportGeneralTypeIssues]
        create_kwargs = {
            "model": self.model,
            "messages": messages,
        }
        try:
            # Some gateway-routed models reject response_format; fall back if so.
            response = resp_create(
                response_format={"type": "json_object"},
                **create_kwargs,
            )
        except Exception as exc:
            if "response_format" in str(exc):
                response = resp_create(**create_kwargs)
            else:
                raise
        return self._response_to_json(response)

    def _process_ocr_text(self, ocr_text: str, source_type: str) -> Dict[str, Any]:
        """Shared helper to log OCR text and run it through the text pipeline."""
        structured_event = self.run_text_pipeline(ocr_text, source_type=source_type)

        print("🔍 OCR text:", file=sys.stderr)
        print(ocr_text, file=sys.stderr)

        return {
            "ocr_text": ocr_text,
            "event": structured_event,
        }

    def run_tesseract_pipeline(self, image_path: Path) -> Dict[str, Any]:
        """
        Extract text from an image using Tesseract OCR and run the structured parsing pipeline.
        """
        ocr_text = self.extract_text_with_tesseract(image_path)
        return self._process_ocr_text(ocr_text, source_type="ocr-tesseract")

    def run_easyocr_pipeline(self, image_path: Path) -> Dict[str, Any]:
        """
        Extract text from an image using EasyOCR and run the structured parsing pipeline.
        """
        ocr_text = self.extract_text_with_easyocr(image_path)
        return self._process_ocr_text(ocr_text, source_type="ocr-easyocr")

    def run_fusion_pipeline(self, image_path: Path) -> Dict[str, Any]:
        """
        Run both OCR engines in parallel, then feed the combined transcript to the parser.
        """
        if not EASYOCR_AVAILABLE:
            raise RuntimeError(
                "EasyOCR is required for OCR fusion. Install it with `pip install easyocr`."
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            tess_future = executor.submit(self.extract_text_with_tesseract, image_path)
            easy_future = executor.submit(self.extract_text_with_easyocr, image_path)
            tesseract_text = tess_future.result()
            easyocr_text = easy_future.result()

        fusion_payload = self._format_fusion_transcript(
            tesseract_text, easyocr_text
        )
        return self._process_ocr_text(fusion_payload, source_type="ocr-fusion")

    @staticmethod
    def extract_text_with_tesseract(image_path: Path) -> str:
        """Use pytesseract (Tesseract OCR) to grab text from the provided screenshot."""
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
    def extract_text_with_easyocr(image_path: Path) -> str:
        """Use EasyOCR to extract text if available."""
        if not EASYOCR_AVAILABLE:
            raise RuntimeError("EasyOCR is not installed. Run `pip install easyocr`.")

        expanded_path = Path(image_path).expanduser().resolve()
        if not expanded_path.exists():
            raise FileNotFoundError(f"Image not found: {expanded_path}")

        reader = easyocr.Reader(['en'], gpu=True)
        result = reader.readtext(str(expanded_path), detail=0)
        cleaned = "\n".join(line.strip() for line in result if line.strip())
        if not cleaned:
            raise RuntimeError("EasyOCR returned no text. Try a clearer screenshot.")
        return cleaned

    @staticmethod
    def _format_fusion_transcript(tesseract_text: str, easyocr_text: str) -> str:
        """Create a demarcated transcript containing both OCR outputs."""
        return dedent(
            f"""
            [Tesseract OCR Transcript]
            ------------------------
            {tesseract_text.strip() or '(no text found)'}

            [EasyOCR OCR Transcript]
            -----------------------
            {easyocr_text.strip() or '(no text found)'}
            """
        ).strip()

    @staticmethod
    def _response_to_json(response: Any) -> Dict[str, Any]:
        """Extract and parse JSON from ChatCompletion response."""
        raw_text = HarmonyStepZero._extract_output_text(response)
        cleaned = raw_text.strip()

        # Handle Markdown ```json fenced code blocks
        if cleaned.startswith("```"):
            # Remove leading ``` or ```json
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1 :]
            # Remove trailing ```
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Model output was not valid JSON:\n{raw_text}"
            ) from exc

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        """
        Extract text content from an OpenAI Responses payload, with a ChatCompletion fallback.
        """
        choices = getattr(response, "choices", None)
        if not choices:
            raise RuntimeError("Could not find text in the model response.")

        first_choice = choices[0]
        message = getattr(first_choice, "message", None) or (
            first_choice.get("message") if isinstance(first_choice, dict) else None
        )
        if not message:
            raise RuntimeError("Completion response missing message content.")

        content = getattr(message, "content", None) or (
            message.get("content") if isinstance(message, dict) else None
        )
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


def _parse_model_arg(raw: str) -> str:
    """Normalize CLI model input to a provider model ID (aliases only)."""
    cleaned = raw.strip().lower()
    if cleaned in MODEL_ALIASES:
        return MODEL_ALIASES[cleaned]
    raise argparse.ArgumentTypeError(
        f"Unsupported model alias '{raw}'. Use --model with one of: "
        f"{', '.join(SUPPORTED_MODELS)} "
        "or use --model-string for an exact provider ID."
    )


def build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Harmony Step 0: text/image to structured event JSON."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    model_help = (
        "LLM model (shorthands) routed through your OpenAI-compatible endpoint "
        f"(default base_url: {DEFAULT_GATEWAY_URL}). "
        "Shorthands: gpt-5-mini|gpt5|5-mini, gpt-4.1-mini|4.1-mini, "
        "gemini|google, grok|xai, deepseek. "
        f"Default model: {DEFAULT_MODEL}. "
        "Use --model-string for any provider ID not covered by these aliases."
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
    model_group = text_parser.add_mutually_exclusive_group()
    model_group.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        type=_parse_model_arg,
        help=model_help,
    )
    model_group.add_argument(
        "--model-string",
        default=None,
        help=model_string_help,
    )

    ocr_tess_parser = subparsers.add_parser(
        "ocr-tesseract", help="Use Tesseract OCR to extract text from an image."
    )
    ocr_tess_parser.add_argument(
        "image_path",
        nargs="?",
        type=Path,
        help="Path to the screenshot that contains the plan details. Prompts interactively if omitted.",
    )
    tess_model_group = ocr_tess_parser.add_mutually_exclusive_group()
    tess_model_group.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        type=_parse_model_arg,
        help=model_help,
    )
    tess_model_group.add_argument(
        "--model-string",
        default=None,
        help=model_string_help,
    )

    ocr_easy_parser = subparsers.add_parser(
        "ocr-easyocr", help="Use EasyOCR to extract text from an image."
    )
    ocr_easy_parser.add_argument(
        "image_path",
        nargs="?",
        type=Path,
        help="Path to the screenshot. Prompts interactively if omitted.",
    )
    easy_model_group = ocr_easy_parser.add_mutually_exclusive_group()
    easy_model_group.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        type=_parse_model_arg,
        help=model_help,
    )
    easy_model_group.add_argument(
        "--model-string",
        default=None,
        help=model_string_help,
    )

    ocr_fusion_parser = subparsers.add_parser(
        "ocr-fusion",
        help="Run Tesseract and EasyOCR in parallel, then fuse the transcripts.",
    )
    ocr_fusion_parser.add_argument(
        "image_path",
        nargs="?",
        type=Path,
        help="Path to the screenshot. Prompts interactively if omitted.",
    )
    fusion_model_group = ocr_fusion_parser.add_mutually_exclusive_group()
    fusion_model_group.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        type=_parse_model_arg,
        help=model_help,
    )
    fusion_model_group.add_argument(
        "--model-string",
        default=None,
        help=model_string_help,
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
    elif args.command in {"ocr-tesseract", "ocr-easyocr", "ocr-fusion"}:
        prompt_map = {
            "ocr-tesseract": "Enter path to screenshot image (Tesseract): ",
            "ocr-easyocr": "Enter path to screenshot image (EasyOCR): ",
            "ocr-fusion": "Enter path to screenshot image (Fusion OCR): ",
        }
        image_path_arg = _resolve_image_path(
            args.image_path,
            prompt_map[args.command],
        )

    try:
        model_arg = getattr(args, "model", DEFAULT_MODEL)
        model_string_arg = getattr(args, "model_string", None)
        allow_unknown_model = False
        selected_model = model_arg
        if model_string_arg is not None:
            selected_model = model_string_arg.strip()
            allow_unknown_model = True

        harmony = HarmonyStepZero(
            model=selected_model,
            allow_unknown_model=allow_unknown_model,
        )
        if message_text is not None:
            result = harmony.run_text_pipeline(message_text)
        else:
            assert image_path_arg is not None
            if args.command == "ocr-easyocr":
                result = harmony.run_easyocr_pipeline(image_path_arg)
            elif args.command == "ocr-tesseract":
                result = harmony.run_tesseract_pipeline(image_path_arg)
            elif args.command == "ocr-fusion":
                result = harmony.run_fusion_pipeline(image_path_arg)
        print("✅ Parsed result:")
        print(json.dumps(result, indent=2))
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
