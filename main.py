import argparse
import json
import pdfplumber
import os
from openai import OpenAI
import sys
from typing import List, Dict
from dotenv import load_dotenv

# Configuration
MODEL_CLEAN = "gpt-4o-mini"
MODEL_SUMMARIZE = "gpt-4o-mini"
CHUNK_CHARS = 3000
TEMPERATURE = 0.0

# System Prompts
CLEAN_SYSTEM = """
You are a precise text cleaner for financial documents.
Reconstruct raw PDF text into readable paragraphs:
- Fix broken lines and hyphenations
- Preserve logical section headers if present
- Keep numbers, symbols, and percentages as-is (e.g., "$78.9 billion", "92.3%")
- Remove page numbers, footers, and table artifacts
Return ONLY cleaned text.
"""

SUM_SYS = """
You are an analyst assistant. Given cleaned financial report text, produce concise JSON with keys:
- "Risks": array of short bullet strings (concise)
- "Opportunities": array of short bullet strings
- "Trends": array of short bullet strings
Do not include explanations outside JSON. Be extractive and factual.
"""

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def call_gpt(system_prompt, user_prompt, model, max_tokens):

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ],
        temperature=TEMPERATURE,
        max_tokens=max_tokens,
    )
    text = resp.choices[0].message.content

    usage = {
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
        "total_tokens": resp.usage.total_tokens,
    }

    return {"text": text, "usage": usage}

def extract_text_from_pdf(filename):
    text = ""
    with pdfplumber.open(filename) as pdf:
        for page in pdf.pages:
            text += page.extract_text() + "\n"
    return text

def chunk_text(s, max_chars):
    s = s.replace("\r", "")
    chunks = []
    i = 0
    while i < len(s):
        chunk = s[i:i+max_chars]
        j = chunk.rfind("\n")
        if j > 0 and (i + j) < (i + max_chars - 250):
            chunks.append(chunk[:j]) # Cut at newline if not too close to chunk end
            i += j + 1
        else:
            chunks.append(chunk)
            i += max_chars
    return chunks

def clean_chunk(raw_text):
    prompt = f"Raw text to clean:\n\n{raw_text}"
    return call_gpt(CLEAN_SYSTEM, prompt, model=MODEL_CLEAN, max_tokens=1200)

def summarize_chunk(cleaned_text):
    prompt = f"""
        Analyze the cleaned text and return JSON with "Risks", "Opportunities", "Trends".
        Keep each bullet short (8-15 words), factual, and specific.

        Cleaned text:
        {cleaned_text}
        """
    return call_gpt(SUM_SYS, prompt, MODEL_SUMMARIZE, 900)

def safe_parse_json(s):
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(s[start:end+1])
            except Exception:
                pass
    return {"Risks": [], "Opportunities": [], "Trends": []}

def merge_lists(*lists):
    out = []
    for L in lists:
        for item in L:
            out.append(item.strip())
    return out

def merge_summaries(parts):
    risks, opps, trends = [], [], []
    for p in parts:
        risks = merge_lists(risks, p.get("Risks", []))
        opps = merge_lists(opps, p.get("Opportunities", []))
        trends = merge_lists(trends, p.get("Trends", []))
    return {"Risks": risks, "Opportunities": opps, "Trends": trends}

def render_markdown(company, title, summary):
    md = [f"# {company} – {title} (AI Summary)\n"]
    for section in ["Risks", "Opportunities", "Trends"]:
        md.append(f"## {section}")
        items = summary.get(section, [])
        if not items:
            md.append("- (none)")
        else:
            for b in items:
                md.append(f"- {b}")
        md.append("") 
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(description="Summarize a financial PDF into Risks/Opportunities/Trends")
    parser.add_argument("file", help="Path to PDF (e.g., costco.pdf)")
    parser.add_argument("--company", default="Company", help="Company name for output labeling")
    parser.add_argument("--title", default="Report", help="Report title/period (e.g., Q4 FY2025)")
    parser.add_argument("--outbase", default="summary", help="Output basename (without extension)")
    args = parser.parse_args()

    raw_text = extract_text_from_pdf(args.file)
    if not raw_text.strip():
        print("No text extracted from PDF (check the file).", file=sys.stderr)
        sys.exit(2)

    raw_chunks = chunk_text(raw_text, 1500)
    total_tokens_in = total_tokens_out = 0

    # Clean
    cleaned_chunks = []
    for chunk in raw_chunks:
        resp = clean_chunk(chunk)
        cleaned_chunks.append(resp["text"])
        u = resp["usage"]
        total_tokens_in += u["prompt_tokens"]
        total_tokens_out += u["completion_tokens"]

    cleaned_text = "\n\n".join(cleaned_chunks)
    with open(f"{args.outbase}_clean.txt", "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    # Summarize
    sum_chunks = chunk_text(cleaned_text, 1500)
    partial_summaries = []
    for chunk in sum_chunks:
        resp = summarize_chunk(chunk)
        u = resp["usage"]
        total_tokens_in += u["prompt_tokens"]
        total_tokens_out += u["completion_tokens"]
        parsed = safe_parse_json(resp["text"])
        partial_summaries.append(parsed)

    merged = merge_summaries(partial_summaries)
    with open(f"{args.outbase}.json", "w", encoding="utf-8") as jf:
        json.dump({
            "Company": args.company,
            "Title": args.title,
            **merged
        }, jf, indent=2, ensure_ascii=False)

    md = render_markdown(args.company, args.title, merged)
    with open(f"{args.outbase}.md", "w", encoding="utf-8") as mf:
        mf.write(md)

    print("Done.")
    print(f"Chunks cleaned: {len(raw_chunks)} | Chunks summarized: {len(sum_chunks)}")
    print(f"Token usage - prompt: {total_tokens_in}, completion: {total_tokens_out}")
    print(f"Wrote: {args.outbase}_clean.txt, {args.outbase}.json, {args.outbase}.md")


if __name__ == "__main__":
    main()