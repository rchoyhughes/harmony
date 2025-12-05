from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from app.harmony_engine import HarmonyPipeline, Settings  # noqa: E402
from app.harmony_engine.core.models import (  # noqa: E402
    ImageParseResponse,
    OCRMode,
    TextParseRequest,
    TextParseResponse,
)

settings = Settings()  # type: ignore[call-arg]  # Pydantic BaseSettings accepts env/.env
pipeline = HarmonyPipeline(settings)

app = FastAPI(
    title="Harmony Step 1 Server",
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
        OCRMode.FUSION,
        description="ocr-tesseract | ocr-easyocr | ocr-fusion (default fusion)",
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

