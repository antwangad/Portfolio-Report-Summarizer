# Portfolio-Report-Summarizer

This tool extracts text from financial PDF reports, cleans it for readability, and generates concise summaries of Risks, Opportunities, and Trends using GPT.

## Features

- Extracts text from PDFs with pdfplumber

- Cleans raw text with GPT (via OpenAI API)

- Summarizes insights with GPT (via OpenAI API)

- Outputs results as:

    - Cleaned text (.txt)

    - JSON structured summary (.json)

    - Readable Markdown report (.md)

## Usage
```bash
python main.py costco.pdf --company "Costco" --title Q4-FY2025 --outbase "output1"
```

## Requirements
- Python 3.9+

- OpenAI API key in .env:
    ```ini
    OPENAI_API_KEY=your_key_here
    ```

## Example Output

- output1.txt → cleaned raw text

- output1.json → structured summary

- output1.md → easy-to-read Markdown