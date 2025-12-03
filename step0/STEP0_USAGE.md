# Harmony Phase 0 Usage

This prototype shows the end-to-end intake pipeline: raw text or a screenshot in, structured JSON out. Follow the steps below to try it yourself.

## 1. Install requirements

```bash
cd /Users/rchoyhughes/projects/harmony/step0
pip install -r requirements.txt
```

Install Tesseract so OCR works (macOS example):

```bash
brew install tesseract
```

## 2. Configure the OpenAI API key

Create `/Users/rchoyhughes/projects/harmony/.env` with:

```
OPENAI_API_KEY=sk-...
```

## 3. Parse a raw text message

```bash
cd /Users/rchoyhughes/projects/harmony/step0
python step0_prototype.py text "Tim: Wanna do dinner at 7 next Tuesday at Garden Carver?"
```

The script prints structured JSON describing the tentative event (title, fuzzy time window, location, participants, notes, follow-ups).

## 4. Parse a screenshot

```bash
cd /Users/rchoyhughes/projects/harmony/step0
python step0_prototype.py image /absolute/path/to/imessage_screenshot.png
```

The script will:

1. Run OCR via pytesseract to extract the conversation text.
2. Send the text through the same GPT-4.1-mini parsing pipeline.
3. Output both the OCR text and the structured event JSON.

## 5. Troubleshooting

- **Missing API key:** make sure `.env` exists and contains `OPENAI_API_KEY`.
- **Tesseract not found:** install it and ensure the `tesseract` binary is on your PATH (or set `TESSERACT_CMD`).
- **Empty OCR text:** try a clearer screenshot or increase contrast before rerunning.

That’s the entire Phase 0 flow—no UI, no iOS, just the intake logic we’ll embed later.***

