import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "daily_short_state.json"
ARCHIVE_ROOT = BASE_DIR / "batches" / "daily_private"
QC_REVIEW_DIR = BASE_DIR / "qc_review"

TOPICS = [
    "Aileen Wuornos",
    "BTK Killer",
    "Son of Sam",
    "John Wayne Gacy",
    "The Black Dahlia",
    "Lizzie Borden",
    "The Zodiac Killer",
    "H.H. Holmes",
    "The Craigslist Killer",
    "The Villisca Axe Murders",
]

ARTIFACTS = [
    "short_video.mp4",
    "short_script.txt",
    "audio.mp3",
    "timestamps.json",
    "image_prompts.json",
    "metadata.json",
    "title.txt",
    "description.txt",
    "hashtags.txt",
    "thumbnail.png",
    "music.wav",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate one premium YouTube short, QC it, and upload it privately.")
    parser.add_argument("--topic", default="", help="Optional explicit topic.")
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {"topic_index": 0}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"topic_index": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def slugify(value: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe.strip("-") or "short"


def choose_topic(explicit_topic: str) -> tuple[str, dict]:
    state = load_state()
    if explicit_topic.strip():
        return explicit_topic.strip(), state
    index = int(state.get("topic_index", 0)) % len(TOPICS)
    topic = TOPICS[index]
    state["topic_index"] = (index + 1) % len(TOPICS)
    return topic, state


def run_command(args: list[str], desc: str, dry_run: bool = False) -> None:
    print(f"\n{desc}...")
    print(" ".join(args))
    if dry_run:
        return
    result = subprocess.run(args, cwd=BASE_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"Failed: {desc}")


def archive_outputs(topic: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = ARCHIVE_ROOT / f"{timestamp}_{slugify(topic)}"
    destination.mkdir(parents=True, exist_ok=True)
    for artifact in ARTIFACTS:
        path = BASE_DIR / artifact
        if path.is_file():
            shutil.copy2(path, destination / path.name)
    if QC_REVIEW_DIR.is_dir():
        review_destination = destination / "qc_review"
        if review_destination.exists():
            shutil.rmtree(review_destination)
        shutil.copytree(QC_REVIEW_DIR, review_destination)
    return destination


def main() -> int:
    args = parse_args()
    topic, state = choose_topic(args.topic)
    python = sys.executable

    print(f"Topic selected: {topic}")
    run_command([python, "run_shorts.py", "--topic", topic, "--use-runway", "--qc", "--premium"], "Generating premium short", args.dry_run)

    archive_dir = None
    if not args.dry_run:
        archive_dir = archive_outputs(topic)
        print(f"Artifacts archived to: {archive_dir}")

    if not args.skip_upload:
        run_command(
            [
                python,
                "upload.py",
                "--video", "short_video.mp4",
                "--metadata", "metadata.json",
                "--thumbnail", "thumbnail.png",
                "--privacy", args.privacy,
            ],
            f"Uploading {topic} as {args.privacy}",
            args.dry_run,
        )

    if not args.dry_run:
        state["last_run_at"] = datetime.now().isoformat()
        state["last_topic"] = topic
        save_state(state)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
