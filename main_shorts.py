import argparse
from pathlib import Path

from gemini_cli import run_gemini_cli


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_TOPIC = "Ted Bundy"
DEFAULT_OUTPUT = BASE_DIR / "short_script.txt"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a short-form true crime script with Gemini CLI.")
    parser.add_argument("--tema", default=DEFAULT_TOPIC, help="Short topic.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output script path.")
    parser.add_argument("--premium", action="store_true", help="Use the premium Gemini model chain for higher quality scripts.")
    return parser.parse_args()


def generate_script(topic: str, premium: bool = False) -> str:
    prompt = (
        "You are writing a viral YouTube Shorts true crime script for a U.S. audience. "
        f"Topic: {topic}. "
        "STRUCTURE - follow this exactly: "
        "1) HOOK (first 2 sentences): Open with the single most disturbing or unbelievable fact about this case. "
        "Do NOT say the name yet. Example style: 'He killed 30 people. Nobody noticed for 7 years.' "
        "2) REVEAL: Now say the name and one sentence of context. "
        "3) ESCALATION (3 sharp beats): Each sentence reveals something worse than the last. Short, punchy, no padding. "
        "4) TWIST or DETAIL: One chilling detail most people don't know. "
        "5) PAYOFF: One sentence - the most haunting thing about this case. "
        "6) CTA (1 sentence max): Natural, not corporate. Example: 'Follow for more cases like this.' "
        "Rules: American English only. Every sentence must make the viewer need to hear the next one. "
        "No filler, no intro greeting, no markdown, no bullet points. Maximum 130 words."
    )
    return run_gemini_cli(prompt, premium=premium)


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    script = generate_script(args.tema.strip() or DEFAULT_TOPIC, premium=args.premium)
    output_path.write_text(script, encoding="utf-8")
    print(script)
    print(f"\nShort script saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
