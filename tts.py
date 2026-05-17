import argparse
import asyncio
import json
import re
from pathlib import Path

import edge_tts


DEFAULT_INPUT = "guion.txt"
DEFAULT_OUTPUT = "audio.mp3"
DEFAULT_TIMESTAMPS = "timestamps.json"
DEFAULT_VOICE = "en-US-GuyNeural"
DEFAULT_RATE = "-4%"
DEFAULT_PITCH = "-14Hz"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert script to MP3 audio with word timestamps.")
    parser.add_argument("--input", default=DEFAULT_INPUT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--timestamps", default=DEFAULT_TIMESTAMPS)
    parser.add_argument("--voice", default=DEFAULT_VOICE)
    parser.add_argument("--rate", default=DEFAULT_RATE)
    parser.add_argument("--pitch", default=DEFAULT_PITCH)
    return parser.parse_args()


def normalize_script(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def prepare_tts_script(text: str) -> str:
    return text


async def synthesize_with_timestamps(
    script: str,
    audio_path: Path,
    timestamps_path: Path,
    voice: str,
    rate: str,
    pitch: str,
) -> None:
    communicate = edge_tts.Communicate(
        script,
        voice=voice,
        rate=rate,
        pitch=pitch,
        boundary="WordBoundary",
    )

    word_boundaries: list[dict] = []

    with audio_path.open("wb") as audio_file:
        async for chunk in communicate.stream():
            chunk_type = chunk.get("type")
            if chunk_type == "audio":
                audio_file.write(chunk["data"])
            elif chunk_type == "WordBoundary":
                word = chunk.get("text", "").strip()
                if word and any(c.isalnum() for c in word):
                    word_boundaries.append(
                        {
                            "word": word,
                            "start": chunk["offset"] / 10_000_000,
                            "duration": chunk["duration"] / 10_000_000,
                        }
                    )
    timestamps_path.write_text(
        json.dumps(word_boundaries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Audio guardado en: {audio_path.resolve()}")
    print(f"Timestamps saved to: {timestamps_path.resolve()} ({len(word_boundaries)} words)")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.is_file():
        raise FileNotFoundError(f"Script not found: {input_path.resolve()}")

    script = normalize_script(input_path.read_text(encoding="utf-8"))
    if not script:
        raise ValueError("The script file is empty.")
    tts_script = prepare_tts_script(script)

    asyncio.run(
        synthesize_with_timestamps(
            script=tts_script,
            audio_path=Path(args.output),
            timestamps_path=Path(args.timestamps),
            voice=args.voice,
            rate=args.rate,
            pitch=args.pitch,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
