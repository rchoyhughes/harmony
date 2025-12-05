from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from PIL import Image  # type: ignore[import]
import pytesseract  # type: ignore[import]

# Optional EasyOCR support
try:
    import easyocr  # type: ignore

    EASYOCR_AVAILABLE = True
except Exception:
    EASYOCR_AVAILABLE = False


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

    cleaned = "\n".join(line.strip() for line in raw_text.splitlines() if line.strip())
    if not cleaned:
        raise RuntimeError(
            "OCR succeeded but returned empty text. Try a clearer screenshot."
        )

    return cleaned


def extract_text_with_easyocr(image_path: Path) -> str:
    """Use EasyOCR to extract text if available."""
    if not EASYOCR_AVAILABLE:
        raise RuntimeError("EasyOCR is not installed. Run `pip install easyocr`.")

    expanded_path = Path(image_path).expanduser().resolve()
    if not expanded_path.exists():
        raise FileNotFoundError(f"Image not found: {expanded_path}")

    reader = easyocr.Reader(["en"], gpu=False)
    result = reader.readtext(str(expanded_path), detail=0)
    cleaned = "\n".join(line.strip() for line in result if line.strip())
    if not cleaned:
        raise RuntimeError("EasyOCR returned no text. Try a clearer screenshot.")
    return cleaned


def format_fusion_transcript(tesseract_text: str, easyocr_text: str) -> str:
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

