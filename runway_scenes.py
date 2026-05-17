import argparse
import base64
import json
import mimetypes
import os
import time
from pathlib import Path
from urllib.request import urlretrieve

from dotenv import load_dotenv
from runwayml import RunwayML, TaskFailedError

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
GENERATED_IMAGES_DIR = BASE_DIR / "generated_images"
ANIMATED_SCENES_DIR = BASE_DIR / "animated_scenes"
PROMPTS_FILE = BASE_DIR / "image_prompts.json"
FALLBACK_KEY_FILE = Path(r"C:\Users\yoeld\Desktop\APi_Runway.txt")
DEFAULT_MODEL = "gen4_turbo"
CLIP_DURATION = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animate scene images with Runway image-to-video.")
    parser.add_argument("--images-dir", default=str(GENERATED_IMAGES_DIR))
    parser.add_argument("--output-dir", default=str(ANIMATED_SCENES_DIR))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--duration", type=int, default=CLIP_DURATION)
    return parser.parse_args()


def load_api_key() -> str:
    env_key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    if env_key:
        return env_key
    if FALLBACK_KEY_FILE.is_file():
        return FALLBACK_KEY_FILE.read_text(encoding="utf-8").strip()
    raise RuntimeError("Runway API key not found. Set RUNWAYML_API_SECRET in .env")


def image_to_data_uri(image_path: Path) -> str:
    content_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def load_beat_types() -> dict[int, str]:
    if not PROMPTS_FILE.is_file():
        return {}
    try:
        data = json.loads(PROMPTS_FILE.read_text(encoding="utf-8"))
        return {item["scene"]: item.get("beat_type", "") for item in data if isinstance(item, dict)}
    except Exception:
        return {}


MOTION_MAP = {
    "opening threat": "Slow ominous camera push forward, shadows deepen gradually, tense documentary, no text.",
    "criminal portrait": "Extremely slow camera zoom into the face, near-imperceptible drift, haunting stillness, no text.",
    "false-trust facade": "Gentle camera drift, unsettling calm, soft light flicker on face, no text.",
    "abduction setup": "Slow creeping forward movement, tense atmosphere, dark environment, no text.",
    "violent reveal": "Sharp dramatic push in, high contrast, intense close-up, dark cinematic, no text.",
    "courtroom performance": "Slow deliberate pan, tense courtroom atmosphere, dramatic lighting, no text.",
    "taunting evidence": "Very slow zoom into documents on a dark desk, investigative dread, no text.",
    "crime scene tension": "Slow cinematic drift through dark location, fog, atmospheric dread, no text.",
    "aftermath and legacy": "Slow pull back revealing emptiness and sorrow, haunting mood, no text.",
    "story progression": "Smooth cinematic movement, dark documentary style, tense atmosphere, no text.",
}


def build_motion_prompt(beat_type: str, index: int) -> str:
    for key, prompt in MOTION_MAP.items():
        if key in beat_type.lower():
            return prompt
    fallbacks = [
        "Slow cinematic push forward, dark documentary atmosphere, tense mood, no text.",
        "Gentle camera drift, ominous lighting, true crime aesthetic, no text.",
        "Slow zoom in, dramatic shadows, investigative mood, no text.",
    ]
    return fallbacks[index % len(fallbacks)]


def animate_scenes(
    images_dir: Path,
    output_dir: Path,
    model: str = DEFAULT_MODEL,
    duration: int = CLIP_DURATION,
) -> list[Path]:
    image_paths = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    )
    if not image_paths:
        print("No images found to animate.")
        return []

    api_key = load_api_key()
    client = RunwayML(api_key=api_key)
    beat_types = load_beat_types()

    output_dir.mkdir(parents=True, exist_ok=True)
    for old in output_dir.iterdir():
        if old.suffix.lower() == ".mp4":
            try:
                old.unlink()
            except PermissionError:
                pass

    generated: list[Path] = []
    for index, image_path in enumerate(image_paths):
        beat_type = beat_types.get(index + 1, "story progression")
        motion_prompt = build_motion_prompt(beat_type, index)
        output_path = output_dir / f"scene_{index + 1:02d}.mp4"

        print(f"Animating scene {index + 1}/{len(image_paths)}: {image_path.name} [{beat_type}]")
        try:
            task = client.image_to_video.create(
                model=model,
                prompt_image=image_to_data_uri(image_path),
                prompt_text=motion_prompt,
                ratio="1280:720",
                duration=duration,
            ).wait_for_task_output()

            urls = task.output
            if not urls:
                print(f"  Scene {index + 1}: Runway returned no output, skipping.")
                continue

            urlretrieve(urls[0], output_path)
            print(f"  Saved: {output_path.name}")
            generated.append(output_path)
            time.sleep(2)

        except TaskFailedError as exc:
            print(f"  Scene {index + 1} Runway task failed: {exc}")
        except Exception as exc:
            print(f"  Scene {index + 1} error: {exc}")

    print(f"\nAnimated {len(generated)}/{len(image_paths)} scenes -> {output_dir}")
    return generated


def main() -> int:
    args = parse_args()
    animate_scenes(
        images_dir=Path(args.images_dir),
        output_dir=Path(args.output_dir),
        model=args.model,
        duration=args.duration,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
