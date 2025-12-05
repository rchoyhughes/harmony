# Harmony Step 1 (API-ready split)

This step refactors the Phase 0 monoscript into small, testable modules and exposes a FastAPI service for parsing text or screenshots into structured event JSON.

## Layout
- `harmony/config.py` — settings and env loading (`.env` at repo root)
- `harmony/models.py` — model IDs/aliases, request/response models, enums
- `harmony/prompts.py` & `harmony/system_prompt.md` — system prompt loader and content
- `harmony/llm.py` — OpenAI-compatible client wrapper
- `harmony/ocr.py` — OCR helpers (Tesseract, optional EasyOCR)
- `harmony/pipeline.py` — orchestration: text + OCR pipelines
- `main.py` — FastAPI app with POST endpoints
- `cli.py` — CLI entry point

## Quickstart
```bash
cd /Users/rchoyhughes/projects/harmony/step1
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ensure /Users/rchoyhughes/projects/harmony/.env has:
# VERCEL_AI_GATEWAY_API_KEY=...
# Optional: VERCEL_AI_GATEWAY_URL=...

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API
- `POST /parse/text` — JSON body: `{ "text": "...", "model": "gpt-5-mini", "model_string": "openai/gpt-5-mini" }` (`model_string` takes precedence; `model` uses shorthands). Response: `{ "event": { ...LLM JSON... } }`.
- `POST /parse/image` — multipart form: file upload field `file`; query params `ocr_mode` (`ocr-tesseract` | `ocr-easyocr` | `ocr-fusion`), optional `model`, `model_string`. Response: `{ "ocr_text": "...", "event": { ...LLM JSON... } }`.

## CLI
From `/Users/rchoyhughes/projects/harmony/step1`:
```bash
python cli.py text "Tim: Wanna do dinner at 7 next Tuesday?"
python cli.py ocr-tesseract /absolute/path/to/screenshot.png
python cli.py ocr-easyocr /absolute/path/to/screenshot.png
python cli.py ocr-fusion /absolute/path/to/screenshot.png
```
Add `--model` shorthands or `--model-string` for an exact provider ID; omit the path to be prompted interactively.

