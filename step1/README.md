# Harmony Step 1 (API-ready split)

This step refactors the Phase 0 monoscript into small, testable modules and exposes a FastAPI service for parsing text or screenshots into structured event JSON.

## Layout

- `app/` — deployable bundle
  - `app/harmony_engine/` — reusable engine (config, models, prompts, llm, ocr, parsing)
  - `app/server/` — Harmony HTTP service (FastAPI + CLI) that depends on `harmony_engine`
    - `main.py` — FastAPI app with POST endpoints
    - `cli.py` — CLI entry point

## Quickstart

```bash
cd /Users/rchoyhughes/projects/harmony/step1
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ensure /Users/rchoyhughes/projects/harmony/step1/app/.env has:
# VERCEL_AI_GATEWAY_API_KEY=...
# Optional: VERCEL_AI_GATEWAY_URL=...

cd app/server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API (server/)

- `POST /parse/text` — JSON body: `{ "text": "...", "model": "gemini", "model_string": "google/gemini-2.5-flash" }` (`model_string` takes precedence; `model` uses shorthands, default is `gemini`; they are mutually exclusive). Response: `{ "event": { ...LLM JSON... } }`.
- `POST /parse/image` — multipart form: file upload field `file`; query params `ocr_mode` (`ocr-tesseract` | `ocr-easyocr` | `ocr-fusion`, default `ocr-fusion`), optional `model`, `model_string` (default `gemini`; mutually exclusive). Response: `{ "ocr_text": "...", "event": { ...LLM JSON... } }`.

## CLI (server/)

From `/Users/rchoyhughes/projects/harmony/step1`:

```bash
python -m app.server.cli text "Tim: Wanna do dinner at 7 next Tuesday?"
python -m app.server.cli ocr-tesseract /absolute/path/to/screenshot.png
python -m app.server.cli ocr-easyocr /absolute/path/to/screenshot.png
python -m app.server.cli ocr-fusion /absolute/path/to/screenshot.png
```

Add `--model` shorthands or `--model-string` for an exact provider ID; omit the path to be prompted interactively.
