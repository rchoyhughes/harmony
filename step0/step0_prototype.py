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
    python step0_prototype.py tesseract /path/to/imessage_screenshot.png
    python step0_prototype.py easyocr /path/to/imessage_screenshot.png

Prereqs:
    - Install dependencies: pip install -r requirements.txt
    - Create a .env file with OPENAI_API_KEY=... in the root directory of the Harmony project
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
today = datetime.now(zoneinfo.ZoneInfo(TIMEZONE)).date().isoformat()

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
    - The user message will always begin with a line like "Source type: text" or
      "Source type: ocr".
    - "text" means the content was provided directly by the user as plain text.
    - "ocr" means the content was extracted from a screenshot or image via OCR.
    - When Source type is "ocr", be especially cautious about lines that look
      like chat app metadata (timestamps, delivery labels, etc.). These may be
      UI artifacts rather than actual event details.

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
    - If someone is directly invited (e.g. "if you wanna come", "do you wanna go",
      "you should come") and they have NOT explicitly declined, you should treat
      them as a likely participant and include their name in participants.
    - If the speaker clearly expresses interest or tentative agreement (e.g.
      "I think I'm free", "that looks cool", "I'm down"), you may treat them as
      a likely participant as well.
    - Do NOT include generic groups such as "friends", "coworkers", "people"
      in participants. Instead, mention them in notes (e.g. "with some friends").
    - If someone explicitly says they cannot attend (e.g. "I can't make it",
      "I won't be there"), do NOT include them in participants, but you may
      describe that fact in notes.
    - Participants may be an empty array only if there are truly no clear
      attendees (for example, brainstorming possibilities without any agreement).

    Notes and follow-up actions:
    - Use notes for short, neutral summaries or important context (e.g.
      "Invitation to a concert on December 5; time not specified.").
    - You do NOT know which participant is the app "user" or who is speaking.
      Avoid using first- or second-person language such as "I", "me", "we",
      "you", or "user" in notes or follow_up_actions.
    - When invitations or plans are mentioned, do NOT state or imply who invited
      whom or who the invitation is directed to. Do not use phrases like
      "X invited Y" or "an invitation was extended to Tim". Instead, describe
      the situation in fully neutral terms, such as "there is an invitation to
      attend a concert involving Tim and a group of friends" or "the
      conversation discusses going to the event together".
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

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
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
        structured_event = self.run_text_pipeline(ocr_text, source_type="ocr")

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
    def extract_text_with_easyocr(image_path: Path) -> str:
        """Use EasyOCR to extract text if available."""
        if not EASYOCR_AVAILABLE:
            raise RuntimeError("EasyOCR is not installed. Run `pip install easyocr`.")

        expanded_path = Path(image_path).expanduser().resolve()
        if not expanded_path.exists():
            raise FileNotFoundError(f"Image not found: {expanded_path}")

        reader = easyocr.Reader(['en'], gpu=False)
        result = reader.readtext(str(expanded_path), detail=0)
        cleaned = "\n".join(line.strip() for line in result if line.strip())
        if not cleaned:
            raise RuntimeError("EasyOCR returned no text. Try a clearer screenshot.")
        return cleaned

    @staticmethod
    def _response_to_json(response: Any) -> Dict[str, Any]:
        """Extract and parse JSON from ChatCompletion response."""
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
        Extract text content from a ChatCompletion response.
        """
        choices = getattr(response, "choices", None)
        if choices and len(choices) > 0:
            first_choice = choices[0]
            message = getattr(first_choice, "message", None)
            if message:
                content = getattr(message, "content", None)
                if isinstance(content, str):
                    return content
                if isinstance(content, Iterable) and not isinstance(content, str):
                    chunks: list[str] = []
                    for part in content:
                        if isinstance(part, str):
                            chunks.append(part)
                        elif isinstance(part, dict):
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

    tesseract_parser = subparsers.add_parser(
        "tesseract", help="Use Tesseract OCR to extract text from an image."
    )
    tesseract_parser.add_argument(
        "image_path",
        nargs="?",
        type=Path,
        help="Path to the screenshot that contains the plan details. If omitted, you will be prompted interactively.",
    )
    tesseract_parser.add_argument(
        "--model",
        default="gpt-4.1-mini",
        help="Override the OpenAI model (default: gpt-4.1-mini).",
    )

    easyocr_parser = subparsers.add_parser(
        "easyocr", help="Use EasyOCR to extract text from the image instead of Tesseract."
    )
    easyocr_parser.add_argument(
        "image_path",
        nargs="?",
        type=Path,
        help="Path to the screenshot. If omitted, prompts interactively.",
    )
    easyocr_parser.add_argument(
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
    elif args.command == "tesseract":
        if args.image_path is not None:
            image_path_arg = args.image_path
        else:
            # Interactive mode for image path
            try:
                raw_path = input("Enter path to screenshot image (Tesseract): ").strip()
            except EOFError:
                raise ValueError("No image path provided.")
            if not raw_path:
                raise ValueError("No image path provided.")

            # Strip leading/trailing ASCII and smart quotes if the user entered them
            raw_path = raw_path.strip("'\u2019\u2018\"\u201c\u201d")

            image_path_arg = Path(raw_path)
    elif args.command == "easyocr":
        if args.image_path is not None:
            image_path_arg = args.image_path
        else:
            try:
                raw_path = input("Enter path to screenshot image (EasyOCR): ").strip()
            except EOFError:
                raise ValueError("No image path provided.")
            if not raw_path:
                raise ValueError("No image path provided.")
            raw_path = raw_path.strip("'\u2019\u2018\"\u201c\u201d")
            image_path_arg = Path(raw_path)

    try:
        harmony = HarmonyStepZero(model=args.model)
        if message_text is not None:
            result = harmony.run_text_pipeline(message_text)
        else:
            assert image_path_arg is not None
            if args.command == "easyocr":
                ocr_text = HarmonyStepZero.extract_text_with_easyocr(image_path_arg)
                # Mirror Tesseract logging: show raw OCR output
                print("🔍 OCR text:", file=sys.stderr)
                print(ocr_text, file=sys.stderr)
                structured = harmony.run_text_pipeline(ocr_text, source_type="ocr")
                result = {"ocr_text": ocr_text, "event": structured}
            elif args.command == "tesseract":
                result = harmony.run_image_pipeline(image_path_arg)
        print("✅ Parsed result:")
        print(json.dumps(result, indent=2))
    except Exception as exc:  # pragma: no cover - CLI convenience
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
