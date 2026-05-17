import argparse
import shutil
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = BASE_DIR / "batches"
DEFAULT_TOPICS = [
    "Ted Bundy",
    "Jeffrey Dahmer",
    "Richard Ramirez",
    "John Wayne Gacy",
    "Zodiac Killer",
]


def slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "short"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and upload a batch of YouTube Shorts.")
    parser.add_argument("--privacy", default="public", choices=["private", "unlisted", "public"])
    parser.add_argument("--single-image", action="store_true", default=True)
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    parser.add_argument("--topics", nargs="*", default=DEFAULT_TOPICS)
    return parser.parse_args()


def run(args: list[str], desc: str) -> None:
    print(f"\n{desc}...")
    result = subprocess.run(args, cwd=BASE_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"Failed: {desc}")


def clear_dir(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    python = sys.executable
    batch_dir = Path(args.output_root) / "shorts_batch_2026_05_10"
    batch_dir.mkdir(parents=True, exist_ok=True)

    run([python, "music.py"], "Generating shared suspense music")

    for index, topic in enumerate(args.topics, start=1):
        slug = f"{index:02d}_{slugify(topic)}"
        item_dir = batch_dir / slug
        item_dir.mkdir(parents=True, exist_ok=True)

        script_path = item_dir / "short_script.txt"
        audio_path = item_dir / "audio.mp3"
        timestamps_path = item_dir / "timestamps.json"
        prompts_path = item_dir / "image_prompts.json"
        images_dir = item_dir / "generated_images"
        thumb_prompt_path = item_dir / "thumbnail_prompt.json"
        thumbnail_path = item_dir / "thumbnail.png"
        title_path = item_dir / "title.txt"
        description_path = item_dir / "description.txt"
        hashtags_path = item_dir / "hashtags.txt"
        metadata_path = item_dir / "metadata.json"
        video_path = item_dir / "short_video.mp4"

        clear_dir(images_dir)

        run([python, "main_shorts.py", "--tema", topic, "--output", str(script_path)], f"[{index}/5] Generating script for {topic}")
        run([python, "tts.py", "--input", str(script_path), "--output", str(audio_path), "--timestamps", str(timestamps_path)], f"[{index}/5] Generating voice for {topic}")
        run(
            [
                python,
                "images.py",
                "--script", str(script_path),
                "--timestamps", str(timestamps_path),
                "--prompts", str(prompts_path),
                "--output-dir", str(images_dir),
                "--thumb-prompt", str(thumb_prompt_path),
                "--thumbnail", str(thumbnail_path),
                "--topic", topic,
                "--scene-count", "4",
            ],
            f"[{index}/5] Preparing image prompts for {topic}",
        )
        run(
            [
                python,
                "metadata.py",
                "--script", str(script_path),
                "--topic", topic,
                "--title-file", str(title_path),
                "--description-file", str(description_path),
                "--hashtags-file", str(hashtags_path),
                "--metadata-file", str(metadata_path),
                "--thumbnail", str(thumbnail_path),
            ],
            f"[{index}/5] Generating metadata for {topic}",
        )

        video_cmd = [
            python,
            "video_shorts.py",
            "--audio", str(audio_path),
            "--timestamps", str(timestamps_path),
            "--prompts", str(prompts_path),
            "--images-dir", str(images_dir),
            "--topic", topic,
            "--output", str(video_path),
        ]
        if args.single_image:
            video_cmd.append("--single-image")
        run(video_cmd, f"[{index}/5] Rendering short for {topic}")

        run(
            [
                python,
                "upload.py",
                "--video", str(video_path),
                "--thumbnail", str(thumbnail_path),
                "--metadata", str(metadata_path),
                "--privacy", args.privacy,
            ],
            f"[{index}/5] Uploading {topic}",
        )

    print(f"\nBatch complete: {batch_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
