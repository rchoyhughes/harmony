# Harmony Phase 0 Usage

This prototype demonstrates Harmony’s intake pipeline: raw text or a screenshot goes in, structured event JSON comes out. Follow these steps to try it out.

## 1. Set up the virtual environment

Create and activate a Python virtual environment:

```bash
cd /Users/[path-to-projects]/harmony/step0
python3 -m venv venv
```

Then activate it and install dependencies:

```bash
source venv/bin/activate  # On macOS/Linux
# or: venv\Scripts\activate  # On Windows
pip install -r requirements.txt
```

Install Tesseract so OCR works (macOS example):

```bash
brew install tesseract
```

## 2. Configure the Vercel AI Gateway credentials

Create `/Users/rchoyhughes/projects/harmony/.env` with your OpenAI-compatible Vercel AI Gateway endpoint and key:

```
VERCEL_AI_GATEWAY_API_KEY=...
VERCEL_AI_GATEWAY_URL=https://<your-gateway-host>/v1/<project>/openai
```

(Both values are required for the LLM parsing step.)

## 3. Parse a raw text message (inline or interactive)

You can parse text either by passing it inline or by entering it interactively:

```bash
python step0_prototype.py text "Tim: Wanna do dinner at 7 next Tuesday at Garden Carver?"
```

Add `--model` to select a Vercel AI Gateway model (default: `openai/gpt-5-mini`). Supported options: `openai/gpt-5-mini`, `openai/gpt-4.1-mini`, `google/gemini-2.5-flash`, `xai/grok-4.1-fast-reasoning`.

```bash
python step0_prototype.py text --model openai/gpt-4.1-mini "Tim: Wanna do dinner at 7 next Tuesday at Garden Carver?"
```

Or run it with no text to enter it interactively:

```bash
python step0_prototype.py text
Enter text to parse:
> Tim: Wanna do dinner at 7 next Tuesday at Garden Carver?
```

## 4. Parse a screenshot (inline or interactive)

Harmony now exposes three OCR modes:

- **`ocr-tesseract`** — classical OCR, fast and accurate on crisp chat screenshots.
- **`ocr-easyocr`** — deep-learning OCR, better when fonts are stylized or low‑contrast.
- **`ocr-fusion`** — runs Tesseract and EasyOCR in parallel, then fuses both transcripts before parsing.

Each mode funnels into the same Vercel AI Gateway parser (default: `openai/gpt-5-mini`). Use `--model` to pick `openai/gpt-4.1-mini`, `google/gemini-2.5-flash`, or `xai/grok-4.1-fast-reasoning`.

**Examples:**

```bash
python step0_prototype.py ocr-tesseract /absolute/path/to/imessage_screenshot.png
python step0_prototype.py ocr-easyocr   /absolute/path/to/imessage_screenshot.png
python step0_prototype.py ocr-fusion    /absolute/path/to/imessage_screenshot.png
```

**Interactive mode:**

```bash
python step0_prototype.py ocr-tesseract
Enter path to screenshot image (Tesseract):
> /Users/you/Desktop/imessage.png
```

Swap `ocr-tesseract` with `ocr-easyocr` or `ocr-fusion` for the other engines—the prompt text will update automatically.

After OCR completes, Harmony will:
  1. Extract text using the selected OCR engine(s).
  2. Parse the text using the selected Vercel AI Gateway model.
  3. Output the OCR text bundle plus the structured event JSON.

## 5. Troubleshooting

- **Missing API key or URL:** ensure `.env` contains `VERCEL_AI_GATEWAY_API_KEY` and `VERCEL_AI_GATEWAY_URL`.
- **Tesseract missing:** install via Homebrew or ensure the `tesseract` binary is on your PATH.
- **EasyOCR missing:** install with `pip install easyocr`.
- **Empty OCR text:** try a clearer screenshot or adjust contrast.

That’s the entire Phase 0 flow. No UI, no iOS, just the intake logic we’ll embed later.
