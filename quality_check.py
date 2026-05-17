import argparse
import json
import re
from pathlib import Path

import numpy as np
from moviepy.video.io.VideoFileClip import VideoFileClip
from PIL import Image


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VIDEO = BASE_DIR / "short_video.mp4"
DEFAULT_OUTPUT_DIR = BASE_DIR / "qc_review"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quality gate for generated shorts.")
    parser.add_argument("--video", default=str(DEFAULT_VIDEO))
    parser.add_argument("--script", default="")
    parser.add_argument("--metadata", default="")
    parser.add_argument("--topic", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--min-duration", type=float, default=20.0)
    parser.add_argument("--max-duration", type=float, default=45.0)
    parser.add_argument("--min-brightness", type=float, default=16.0)
    parser.add_argument("--min-contrast", type=float, default=12.0)
    parser.add_argument("--min-diversity", type=float, default=8.0)
    parser.add_argument("--allow-static", action="store_true")
    return parser.parse_args()


def sample_times(duration: float, count: int = 8) -> list[float]:
    if duration <= 1:
        return [0.0]
    start = min(1.2, duration * 0.12)
    end = max(duration - 0.6, start)
    if count == 1 or end <= start:
        return [start]
    return [start + (end - start) * i / (count - 1) for i in range(count)]


def frame_stats(frame: np.ndarray) -> dict:
    gray = frame.mean(axis=2)
    return {
        "brightness": float(gray.mean()),
        "contrast": float(gray.std()),
    }


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def has_mojibake(text: str) -> bool:
    bad_tokens = ("Ã", "ï¿½", "â€™", "â€œ", "â€")
    return any(token in text for token in bad_tokens)


def topic_in_text(topic: str, text: str) -> bool:
    if not topic.strip():
        return True
    topic_words = [word for word in re.split(r"[^a-z0-9]+", topic.lower()) if len(word) > 2]
    hay = normalize_text(text)
    return any(word in hay for word in topic_words)


def count_distinct_frames(fingerprints: list[np.ndarray], threshold: float = 4.5) -> int:
    distinct: list[np.ndarray] = []
    for fingerprint in fingerprints:
        if not distinct:
            distinct.append(fingerprint)
            continue
        if all(float(np.mean(np.abs(fingerprint - seen))) >= threshold for seen in distinct):
            distinct.append(fingerprint)
    return len(distinct)


def main() -> int:
    args = parse_args()
    video_path = Path(args.video)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    clip = VideoFileClip(str(video_path))
    report = {
        "video": str(video_path),
        "duration": clip.duration,
        "size": [clip.w, clip.h],
        "frames": [],
        "checks": {},
    }

    times = sample_times(clip.duration)
    brightness_values = []
    contrast_values = []
    fingerprints = []
    for index, t in enumerate(times, start=1):
        frame = clip.get_frame(t)
        stats = frame_stats(frame)
        brightness_values.append(stats["brightness"])
        contrast_values.append(stats["contrast"])
        small = np.array(Image.fromarray(frame.astype("uint8")).resize((24, 24))).mean(axis=2)
        fingerprints.append(small)
        img_path = out_dir / f"frame_{index}_{t:.1f}.png"
        Image.fromarray(frame.astype("uint8")).save(img_path)
        report["frames"].append({
            "time": round(t, 2),
            "brightness": round(stats["brightness"], 2),
            "contrast": round(stats["contrast"], 2),
            "path": str(img_path),
        })

    clip.close()

    report["checks"]["duration_ok"] = args.min_duration <= report["duration"] <= args.max_duration
    bright_frames = sum(1 for value in brightness_values if value >= args.min_brightness)
    average_brightness = float(np.mean(brightness_values)) if brightness_values else 0.0
    report["checks"]["brightness_ok"] = bright_frames >= max(len(brightness_values) - 1, 1) and average_brightness >= (args.min_brightness + 2.0)
    report["checks"]["contrast_ok"] = min(contrast_values) >= args.min_contrast

    static_score = 0.0
    diversity_score = 0.0
    distinct_frames = 1
    if len(fingerprints) > 1:
        diffs = [float(np.mean(np.abs(fingerprints[i] - fingerprints[i - 1]))) for i in range(1, len(fingerprints))]
        static_score = max(diffs) if diffs else 0.0
        diversity_pairs = []
        for i in range(len(fingerprints)):
            for j in range(i + 1, len(fingerprints)):
                diversity_pairs.append(float(np.mean(np.abs(fingerprints[i] - fingerprints[j]))))
        diversity_score = max(diversity_pairs) if diversity_pairs else 0.0
        distinct_frames = count_distinct_frames(fingerprints)
    report["checks"]["static_ok"] = args.allow_static or static_score >= 2.0
    report["checks"]["diversity_ok"] = diversity_score >= args.min_diversity
    report["checks"]["repetition_ok"] = distinct_frames >= max(len(fingerprints) // 2, 3)
    report["static_score"] = round(static_score, 3)
    report["diversity_score"] = round(diversity_score, 3)
    report["distinct_frames"] = distinct_frames

    if args.script:
        script_path = Path(args.script)
        if script_path.is_file():
            script_text = script_path.read_text(encoding="utf-8", errors="replace")
            script_words = [word for word in re.split(r"\s+", script_text.strip()) if word]
            report["checks"]["script_encoding_ok"] = not has_mojibake(script_text)
            report["checks"]["script_topic_ok"] = topic_in_text(args.topic, script_text)
            report["checks"]["script_length_ok"] = 50 <= len(script_words) <= 160
            report["checks"]["script_sentence_ok"] = script_text.strip().endswith((".", "!", "?", "\""))

    if args.metadata:
        metadata_path = Path(args.metadata)
        if metadata_path.is_file():
            metadata_text = metadata_path.read_text(encoding="utf-8", errors="replace")
            report["checks"]["metadata_encoding_ok"] = not has_mojibake(metadata_text)
            report["checks"]["metadata_topic_ok"] = topic_in_text(args.topic, metadata_text)
            report["checks"]["hashtags_present_ok"] = "#" in metadata_text

    passed = all(report["checks"].values())
    report["passed"] = passed
    report_path = out_dir / "qc_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    if not passed:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
