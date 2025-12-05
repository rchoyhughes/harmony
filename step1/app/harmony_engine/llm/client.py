from __future__ import annotations

from datetime import datetime
from textwrap import dedent
from typing import Any, Dict, Iterable

from openai import OpenAI  # type: ignore[import]

from harmony_engine.config import Settings
from harmony_engine.prompts import SYSTEM_PROMPT


class LLMClient:
    """Thin wrapper around an OpenAI-compatible client."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(
            api_key=settings.vercel_ai_gateway_api_key,
            base_url=settings.vercel_ai_gateway_url.rstrip("/"),
        )

    def parse_text(self, text: str, source_type: str, model: str) -> Dict[str, Any]:
        """Send raw text to the LLM and return structured event JSON."""
        if not text or not text.strip():
            raise ValueError("Cannot parse an empty text snippet.")

        today_iso = datetime.now(self.settings.tzinfo).date().isoformat()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": dedent(
                    f"""
                    Source type: {source_type}

                    Source message:
                    \"\"\"{text.strip()}\"\"\"

                    Today's date: {today_iso}
                    Assume the user is in the timezone: {self.settings.timezone}.

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
        create_kwargs = {"model": model, "messages": messages}
        try:
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

    @staticmethod
    def _response_to_json(response: Any) -> Dict[str, Any]:
        """Extract and parse JSON from ChatCompletion response."""
        raw_text = LLMClient._extract_output_text(response)
        cleaned = raw_text.strip()

        # Handle Markdown ```json fenced code blocks
        if cleaned.startswith("```"):
            first_newline = cleaned.find("\n")
            if first_newline != -1:
                cleaned = cleaned[first_newline + 1 :]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        import json

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Model output was not valid JSON:\n{raw_text}") from exc

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

