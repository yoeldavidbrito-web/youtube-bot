import argparse
import re
from pathlib import Path

from gemini_cli import run_gemini_cli


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TOPIC = "The Zodiac Killer in California"
DEFAULT_OUTPUT = BASE_DIR / "guion.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a YouTube script with Gemini CLI.")
    parser.add_argument("--tema", default=DEFAULT_TOPIC, help="Video topic.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output script path.")
    parser.add_argument("--premium", action="store_true", help="Use premium Gemini model for script.")
    return parser.parse_args()


def generar_guion(tema: str, premium: bool = False) -> str:
    prompt = (
        "You are writing a premium English-language true crime YouTube script for a U.S. documentary audience. "
        f"Topic: {tema}. "
        "STRUCTURE — follow this exactly: "
        "1) HOOK (2 sentences max): Open with the single most disturbing or unbelievable fact about this case. "
        "Drop the viewer directly into the most chilling moment. No intro, no name yet. "
        "2) REVEAL: Introduce the name and one sentence establishing time and place. "
        "3) PROLOGUE (2-3 sentences): Put the viewer inside the atmosphere — the location, the era, the tension. "
        "4) STORY BEATS (5-7 beats): Each beat escalates. Short punchy sentences. Build dread. "
        "5) TURNING POINT: The moment that changed everything — an arrest, an evidence break, a survivor, a confession. "
        "6) CHILLING DETAIL: One fact about this case that most people don't know. Make it land. "
        "7) CLOSING REFLECTION (2 sentences): The haunting legacy. Why this case still matters. "
        "8) CTA (1 sentence): Natural documentary-style. Example: 'Subscribe — the next case is even darker.' "
        "Rules: American English only. Cinematic, tight, no filler sentences. Every sentence earns its place. "
        "Plain text only. No markdown. No bullet points. No asterisks. Maximum 320 words."
    )
    raw = run_gemini_cli(prompt, premium=premium)
    output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
    output = re.sub(r'^(Gemini|Model|Assistant)\s*:\s*', '', output, flags=re.MULTILINE)
    return output.strip()


def main() -> int:
    args = parse_args()
    tema = args.tema.strip() or DEFAULT_TOPIC
    output_path = Path(args.output)

    print(f"Generating script about: {tema}\n")
    print("=" * 60)
    guion = generar_guion(tema, premium=args.premium)
    print(guion)
    print("=" * 60)
    output_path.write_text(guion, encoding="utf-8")
    print(f"Script saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
