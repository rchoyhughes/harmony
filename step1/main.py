from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

from harmony.config import Settings
from harmony.models import (
    ImageParseResponse,
    OCRMode,
    TextParseRequest,
    TextParseResponse,
)
from harmony.pipeline import HarmonyPipeline

settings = Settings()
pipeline = HarmonyPipeline(settings)

app = FastAPI(
    title="Harmony Step 1",
    description="Text/OCR to structured event JSON (FastAPI)",
    version="0.1.0",
)


@app.post("/parse/text", response_model=TextParseResponse)
def parse_text(request: TextParseRequest):
    """Parse a raw text snippet into structured event JSON."""
    try:
        event = pipeline.parse_text(
            text=request.text,
            model=request.model,
            model_string=request.model_string,
            source_type=request.source_type,
        )
        return {"event": event}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/parse/image", response_model=ImageParseResponse)
async def parse_image(
    file: UploadFile = File(...),
    ocr_mode: OCRMode = Query(
        OCRMode.TESSERACT,
        description="ocr-tesseract | ocr-easyocr | ocr-fusion",
    ),
    model: str | None = Query(
        None, description="Model shorthand alias (e.g., gpt-5-mini, gemini)."
    ),
    model_string: str | None = Query(
        None, description="Exact provider model ID (takes precedence)."
    ),
):
    """Parse an uploaded screenshot via OCR, then structure it via LLM."""
    data = await file.read()
    try:
        return pipeline.parse_image(
            image_bytes=data,
            ocr_mode=ocr_mode,
            model=model,
            model_string=model_string,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/health", response_model=dict)
def health() -> dict[str, str]:
    return {"status": "ok"}

