# Harmony Phase 0 Usage

This prototype shows the end-to-end intake pipeline: raw text or a screenshot in, structured JSON out. Follow the steps below to try it yourself.

## 1. Set up the virtual environment

A Python virtual environment should be set up in `step0/venv/`. If it doesn't exist, create it:

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

## 2. Configure the OpenAI API key

Create `/Users/rchoyhughes/projects/harmony/.env` with:

```
OPENAI_API_KEY=sk-...
```

## 3. Parse a raw text message (inline or interactive)

You can pass text directly:

```bash
python step0_prototype.py text "Tim: Wanna do dinner at 7 next Tuesday at Garden Carver?"
```

Or run it with no text to enter it interactively:

```bash
python step0_prototype.py text
Enter text to parse:
> Tim: Wanna do dinner at 7 next Tuesday at Garden Carver?
```

## 4. Parse a screenshot (inline or interactive)

Provide an image path directly:

```bash
python step0_prototype.py image /absolute/path/to/imessage_screenshot.png
```
You can also use EasyOCR instead of Tesseract by calling the `easyocr` command:

```bash
python step0_prototype.py easyocr /absolute/path/to/imessage_screenshot.png
```

Or omit the path and you will be prompted interactively:

```bash
python step0_prototype.py image
Enter path to screenshot image:
> /Users/you/Desktop/imessage.png
```

Or interactively with EasyOCR:

```bash
python step0_prototype.py easyocr
Enter path to screenshot image (EasyOCR):
> /Users/you/Desktop/imessage.png
```

The script will then:

1. Run OCR using Tesseract (default) or EasyOCR (if the `easyocr` command was used).
2. Parse the extracted text through the GPT-4.1-mini pipeline.
3. Output both the OCR text and the structured event JSON.

## 5. Troubleshooting

- **Missing API key:** make sure `.env` exists and contains `OPENAI_API_KEY`.
- **Tesseract not found:** install it and ensure the `tesseract` binary is on your PATH (or set `TESSERACT_CMD`).
- **EasyOCR not found:** install it with `pip install easyocr` or use the default `image` command which relies on Tesseract.
- **Empty OCR text:** try a clearer screenshot or increase contrast before rerunning.

That’s the entire Phase 0 flow. No UI, no iOS, just the intake logic we’ll embed later.***
