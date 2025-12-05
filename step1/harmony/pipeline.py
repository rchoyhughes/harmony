from __future__ import annotations

import io
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict

from PIL import Image  # type: ignore[import]

from .config import Settings
from .llm import LLMClient
from .models import OCRMode, resolve_model_choice
from .ocr import (
    EASYOCR_AVAILABLE,
    extract_text_with_easyocr,
    extract_text_with_tesseract,
    format_fusion_transcript,
)


class HarmonyPipeline:
    """Core orchestration for text and OCR parsing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.llm = LLMClient(settings)

    def parse_text(
        self,
        text: str,
        model: str | None,
        model_string: str | None,
        source_type: str = "text",
    ) -> Dict[str, Any]:
        selected_model = resolve_model_choice(model=model, model_string=model_string)
        return self.llm.parse_text(
            text=text, source_type=source_type, model=selected_model
        )

    def parse_image(
        self,
        image_bytes: bytes,
        ocr_mode: OCRMode,
        model: str | None,
        model_string: str | None,
    ) -> Dict[str, Any]:
        """Run OCR then parse the resulting text through the LLM."""
        if not image_bytes:
            raise ValueError("Uploaded image is empty.")

        temp_path = self._write_temp_image(image_bytes)
        try:
            if ocr_mode == OCRMode.TESSERACT:
                ocr_text = extract_text_with_tesseract(temp_path)
                source_type = OCRMode.TESSERACT.value
            elif ocr_mode == OCRMode.EASYOCR:
                ocr_text = extract_text_with_easyocr(temp_path)
                source_type = OCRMode.EASYOCR.value
            elif ocr_mode == OCRMode.FUSION:
                ocr_text = self._run_fusion_ocr(temp_path)
                source_type = OCRMode.FUSION.value
            else:
                raise ValueError(f"Unsupported OCR mode: {ocr_mode}")

            event = self.parse_text(
                text=ocr_text,
                model=model,
                model_string=model_string,
                source_type=source_type,
            )
            return {"ocr_text": ocr_text, "event": event}
        finally:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass

    def _run_fusion_ocr(self, image_path: Path) -> str:
        if not EASYOCR_AVAILABLE:
            raise RuntimeError(
                "EasyOCR is required for OCR fusion. Install it with `pip install easyocr`."
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            tess_future = executor.submit(extract_text_with_tesseract, image_path)
            easy_future = executor.submit(extract_text_with_easyocr, image_path)
            tesseract_text = tess_future.result()
            easyocr_text = easy_future.result()

        return format_fusion_transcript(tesseract_text, easyocr_text)

    @staticmethod
    def _write_temp_image(image_bytes: bytes) -> Path:
        """Persist uploaded bytes to a temp file for OCR engines."""
        buffer = io.BytesIO(image_bytes)
        try:
            with Image.open(buffer) as img:
                format_name = (img.format or "PNG").lower()
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=f".{format_name}"
                ) as temp_file:
                    img.save(temp_file, format=img.format or "PNG")
                    return Path(temp_file.name)
        except Exception as exc:
            raise ValueError("Uploaded file is not a valid image.") from exc

