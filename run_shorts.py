import argparse
import json
import subprocess
import sys
from pathlib import Path

from moviepy.audio.io.AudioFileClip import AudioFileClip


BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Shorts pipeline for a chosen true crime topic.")
    parser.add_argument("--topic", default="Ted Bundy", help="Topic to generate, e.g. 'Zodiac Killer'.")
    parser.add_argument("--use-runway", action="store_true", help="Generate motion background with Runway gen4_turbo.")
    parser.add_argument("--use-luma", action="store_true", help="Generate cinematic scene clips with Luma AI (text-to-video).")
    parser.add_argument("--use-kling", action="store_true", help="Animate a criminal portrait with Kling AI (image-to-video).")
    parser.add_argument("--single-image", action="store_true", help="Render the short with one main fallback image.")
    parser.add_argument("--qc", action="store_true", help="Run quality checks before finishing.")
    parser.add_argument("--premium", action="store_true", help="Use premium Gemini models for the script and metadata.")
    return parser.parse_args()


def run(args: list[str], desc: str) -> None:
    print(f"\n{desc}...")
    result = subprocess.run(args, cwd=BASE_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"Failed: {desc}")


def split_prompt_groups(prompts: list[dict], audio_duration: float) -> list[list[dict]]:
    if not prompts:
        return []
    if audio_duration <= 30 or len(prompts) < 4:
        return [prompts]

    midpoint = audio_duration / 2
    left = [item for item in prompts if float(item.get("start", 0.0)) < midpoint]
    right = [item for item in prompts if float(item.get("start", 0.0)) >= midpoint]
    if not left or not right:
        cut = max(len(prompts) // 2, 1)
        left, right = prompts[:cut], prompts[cut:]
    return [left, right]


def build_segment_prompt(topic: str, beats: list[dict], segment_index: int, segment_count: int) -> str:
    beat_visuals = {
        "violent reveal": "ominous close-up, uneasy expression, lurking danger",
        "crime scene tension": "lonely roadside, distant headlights, investigative tension",
        "story progression": "night travel, motel glow, passing traffic, documentary realism",
        "aftermath and legacy": "case files, courtroom atmosphere, prison corridor, debated legacy",
    }
    beat_types = []
    for beat in beats:
        beat_type = str(beat.get("beat_type", "")).strip()
        if beat_type and beat_type not in beat_types:
            beat_types.append(beat_type)
    visuals = [beat_visuals.get(beat_type, "slow cinematic motion, tense documentary realism") for beat_type in beat_types[:3]]
    joined_visuals = ", ".join(visuals) if visuals else "slow cinematic motion, tense documentary realism"
    return (
        f"Vertical true crime documentary sequence about {topic}. "
        f"This is segment {segment_index} of {segment_count}. "
        f"Focus on a coherent atmosphere with these visual anchors: {joined_visuals}. "
        "Use one continuous cinematic shot with natural motion, readable exposure, dramatic but clear lighting, "
        "no text, no captions, no logos, no collage, no gore, and no repeated motion loops."
    )


def load_clip_jobs(prompts_path: Path, topic: str, audio_duration: float) -> list[dict]:
    if not prompts_path.is_file():
        return []
    try:
        prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(prompts, list) or not prompts:
        return []

    groups = split_prompt_groups(prompts, audio_duration)
    jobs = []
    total_groups = len(groups)
    target_duration = 15 if audio_duration > 30 else 10
    for index, group in enumerate(groups, start=1):
        if not group:
            continue
        jobs.append(
            {
                "filename": f"runway_clip_{index}.mp4",
                "prompt_text": build_segment_prompt(topic, group, index, total_groups),
                "duration": target_duration,
            }
        )
    return jobs


def _get_audio_duration() -> float:
    clip = AudioFileClip(str(BASE_DIR / "audio.mp3"))
    try:
        return clip.duration
    finally:
        clip.close()


def _generate_luma_clips(topic: str, python: str) -> list[str]:
    audio_duration = _get_audio_duration()
    scene_count = 2 if audio_duration > 30 else 1
    clip_targets = []
    for i in range(scene_count):
        filename = f"luma_clip_{i + 1}.mp4"
        run(
            [python, "luma_render.py", "--topic", topic, "--output", filename,
             "--scene-index", str(i), "--ratio", "9:16"],
            f"Generating Luma AI cinematic scene {i + 1}/{scene_count}",
        )
        clip_targets.append(filename)
    return clip_targets


def _generate_kling_clip(topic: str, python: str) -> list[str]:
    run(
        [python, "kling_render.py", "--topic", topic, "--output", "kling_clip.mp4", "--duration", "5"],
        "Animating criminal portrait with Kling AI",
    )
    return ["kling_clip.mp4"]


def _generate_runway_clips(topic: str, python: str) -> list[str]:
    audio_duration = _get_audio_duration()
    runway_jobs = load_clip_jobs(BASE_DIR / "image_prompts.json", topic, audio_duration)
    if not runway_jobs:
        runway_jobs = [{
            "filename": "runway_clip_1.mp4",
            "prompt_text": (
                f"Vertical true crime documentary atmosphere about {topic}, "
                "realistic cinematic motion, readable exposure, no text, no repeated loops."
            ),
            "duration": 10,
        }]
    clip_targets = []
    for job in runway_jobs:
        cmd = [python, "runway_render.py", "--script", "short_script.txt",
               "--topic", topic, "--output", job["filename"], "--duration", str(job["duration"])]
        if job.get("prompt_text"):
            cmd.extend(["--prompt-text", job["prompt_text"]])
        run(cmd, f"Generating Runway motion clip {job['filename']}")
        clip_targets.append(job["filename"])
    return clip_targets


def main() -> int:
    args = parse_args()
    topic = args.topic.strip() or "Ted Bundy"
    python = sys.executable
    using_ai_video = args.use_runway or args.use_luma or args.use_kling

    script_cmd = [python, "main_shorts.py", "--tema", topic]
    if args.premium:
        script_cmd.append("--premium")
    run(script_cmd, "Generating short script")
    run([python, "tts.py", "--input", "short_script.txt"], "Generating short voice")

    images_cmd = [python, "images.py", "--script", "short_script.txt", "--topic", topic, "--scene-count", "6"]
    if using_ai_video:
        images_cmd.append("--prompts-only")
    run(images_cmd, "Generating beat-based image prompts")

    run([python, "music.py", "--profile", "Macabre Tension"], "Generating background music")
    metadata_cmd = [python, "metadata.py", "--script", "short_script.txt", "--topic", topic]
    if args.premium:
        metadata_cmd.append("--premium")
    run(metadata_cmd, "Generating metadata")

    video_cmd = [
        python, "video_shorts.py",
        "--audio", "audio.mp3",
        "--timestamps", "timestamps.json",
        "--prompts", "image_prompts.json",
        "--topic", topic,
    ]

    if args.use_luma:
        clip_targets = _generate_luma_clips(topic, python)
        video_cmd.extend(["--background-video", *clip_targets])
    elif args.use_kling:
        clip_targets = _generate_kling_clip(topic, python)
        video_cmd.extend(["--background-video", *clip_targets])
    elif args.use_runway:
        run([python, "images.py", "--script", "short_script.txt", "--topic", topic,
             "--scene-count", "6", "--prompts-only"], "Generating runway prompts")
        clip_targets = _generate_runway_clips(topic, python)
        video_cmd.extend(["--background-video", *clip_targets])

    if args.single_image:
        video_cmd.append("--single-image")

    run(video_cmd, "Rendering vertical short")

    if args.qc:
        qc_cmd = [
            python, "quality_check.py",
            "--video", "short_video.mp4",
            "--script", "short_script.txt",
            "--metadata", "metadata.json",
            "--topic", topic,
        ]
        if args.single_image or using_ai_video:
            qc_cmd.append("--allow-static")
        run(qc_cmd, "Running quality check")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
