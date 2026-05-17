import argparse
import base64
import json
import os
import re
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCRIPT = BASE_DIR / "guion.txt"
DEFAULT_TIMESTAMPS = BASE_DIR / "timestamps.json"
DEFAULT_PROMPTS = BASE_DIR / "image_prompts.json"
DEFAULT_OUTPUT_DIR = BASE_DIR / "generated_images"
DEFAULT_THUMB_PROMPT = BASE_DIR / "thumbnail_prompt.json"
DEFAULT_THUMB_PATH = BASE_DIR / "thumbnail.png"
DEFAULT_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")
DEFAULT_SCENE_COUNT = 6
MAX_RETRIES = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate scene images and a thumbnail with Gemini.")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT))
    parser.add_argument("--timestamps", default=str(DEFAULT_TIMESTAMPS))
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--thumb-prompt", default=str(DEFAULT_THUMB_PROMPT))
    parser.add_argument("--thumbnail", default=str(DEFAULT_THUMB_PATH))
    parser.add_argument("--topic", default="", help="Video topic.")
    parser.add_argument("--scene-count", type=int, default=DEFAULT_SCENE_COUNT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--prompts-only", action="store_true", help="Only generate prompts/thumbnail prompt, skip image generation.")
    return parser.parse_args()


def normalize_script(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def normalize_word(word: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", word.lower())


def split_into_sentences(script: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", script.strip())
    return [part.strip() for part in parts if part.strip()]


def load_timestamps(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def build_sentence_timings(script: str, timestamps: list[dict]) -> list[dict]:
    sentences = split_into_sentences(script)
    if not sentences:
        return []
    if not timestamps:
        return [{"text": sentence, "start": 0.0, "end": 0.0} for sentence in sentences]

    word_index = 0
    timed_sentences: list[dict] = []
    normalized_timestamps = [normalize_word(item.get("word", "")) for item in timestamps]

    for sentence in sentences:
        sentence_words = [normalize_word(word) for word in sentence.split() if normalize_word(word)]
        if not sentence_words:
            continue

        start_index = None
        current_index = word_index
        matched_indices: list[int] = []
        for target_word in sentence_words:
            while current_index < len(normalized_timestamps) and normalized_timestamps[current_index] != target_word:
                current_index += 1
            if current_index >= len(normalized_timestamps):
                break
            if start_index is None:
                start_index = current_index
            matched_indices.append(current_index)
            current_index += 1

        if start_index is None or not matched_indices:
            continue

        end_index = matched_indices[-1]
        start = timestamps[start_index]["start"]
        end = timestamps[end_index]["start"] + timestamps[end_index]["duration"]
        timed_sentences.append({"text": sentence, "start": start, "end": end})
        word_index = end_index + 1

    return timed_sentences


def is_visual_sentence(text: str) -> bool:
    lower = text.lower()
    blacklist = (
        "subscribe",
        "turn on notifications",
        "join us",
        "until next time",
        "stay safe",
        "to the channel",
    )
    return not any(token in lower for token in blacklist)


def select_story_beats(sentence_timings: list[dict], scene_count: int) -> list[dict]:
    filtered = [item for item in sentence_timings if is_visual_sentence(item["text"])]
    if len(filtered) >= scene_count:
        sentence_timings = filtered

    if not sentence_timings:
        return []
    if len(sentence_timings) <= scene_count:
        return sentence_timings
    if scene_count == 1:
        return [sentence_timings[0]]

    max_index = len(sentence_timings) - 1
    indexes = []
    for i in range(scene_count):
        raw_index = round(i * max_index / (scene_count - 1))
        if raw_index not in indexes:
            indexes.append(raw_index)

    while len(indexes) < scene_count:
        for idx in range(len(sentence_timings)):
            if idx not in indexes:
                indexes.append(idx)
            if len(indexes) >= scene_count:
                break

    return [sentence_timings[idx] for idx in sorted(indexes[:scene_count])]


def infer_subject(topic: str) -> str:
    normalized = topic.lower()
    if "ted bundy" in normalized:
        return "Ted Bundy"
    if "zodiac" in normalized:
        return "the Zodiac Killer"
    if "jeffrey dahmer" in normalized:
        return "Jeffrey Dahmer"
    if "jack the ripper" in normalized:
        return "Jack the Ripper"
    return topic.strip() or "the main subject"


def infer_visual_direction(subject: str, beat_text: str, beat_index: int, beat_count: int) -> tuple[str, str]:
    lower = beat_text.lower()

    # Even-indexed beats: close-up portrait of the criminal (face focused)
    portrait_beats = beat_index % 2 == 0

    if beat_index == 0:
        return (
            "opening threat",
            f"Extreme close-up portrait of {subject}, piercing eyes staring directly at camera, "
            f"half-lit face, dramatic shadow split lighting, photorealistic, sharp facial detail, "
            f"unsettling calm expression, ominous mood",
        )
    if beat_index >= max(beat_count - 2, 1):
        return (
            "aftermath and legacy",
            f"Close-up portrait of {subject} in handcuffs or behind glass, hollow defeated expression, "
            f"hard prison or courtroom lighting, photorealistic, sharp focus on face, haunting legacy",
        )
    if any(token in lower for token in ("court", "attorney", "trial", "judge", "jury", "camera")):
        return (
            "courtroom performance",
            f"Close-up portrait of {subject} inside a courtroom, cold calculated expression, "
            f"sharp focus on face and eyes, tense legal atmosphere, photorealistic",
        )
    if any(token in lower for token in ("charming", "smile", "friendly", "help", "kind", "normal", "charismatic", "polite")):
        return (
            "false-trust facade",
            f"Close-up portrait of {subject}, disarming smile masking danger, soft lighting, "
            f"approachable public persona, sharp focus on face, photorealistic, unsettling undertone",
        )
    if any(token in lower for token in ("stab", "knife", "blood", "attack", "kill", "murder", "slaughter", "weapon", "violent", "brutal")):
        return (
            "violent reveal",
            f"Close-up portrait of {subject}, cold predatory eyes, jaw set, predatory stillness, "
            f"dark dramatic lighting, sharp focus on face, photorealistic, threatening expression",
        )
    if any(token in lower for token in ("letter", "cipher", "newspaper", "phone call", "message")):
        return (
            "taunting evidence",
            f"Close-up of handwritten evidence — letters or ciphers connected to {subject}, "
            f"dark desk, dramatic spotlight, photorealistic, sharp detail, investigative dread",
        )
    if any(token in lower for token in ("park", "car", "road", "night", "lane", "lake", "street", "campus")):
        return (
            "crime scene tension",
            f"Cinematic wide shot of the crime location connected to {subject} at night, "
            f"fog, isolation, harsh shadow, photorealistic, no people, atmospheric dread",
        )
    if portrait_beats:
        return (
            "criminal portrait",
            f"Ultra sharp close-up portrait of {subject}, face filling most of the frame, "
            f"intense direct gaze, split dramatic lighting, photorealistic, high contrast, "
            f"dark background, emotionally charged expression",
        )
    return (
        "story progression",
        f"Mid-shot of {subject} in a setting that matches the narration, "
        f"cinematic framing, sharp focus, dramatic lighting, photorealistic, emotionally precise",
    )


def build_scene_prompts(topic: str, script: str, timestamps: list[dict], scene_count: int) -> list[dict]:
    beats = select_story_beats(build_sentence_timings(script, timestamps), scene_count)
    subject = infer_subject(topic)
    prompts = []
    for index, beat in enumerate(beats, start=1):
        beat_type, visual_direction = infer_visual_direction(subject, beat["text"], index - 1, len(beats))
        prompt = (
            f"Create a cinematic 16:9 documentary scene about '{topic}'. "
            f"Scene {index}. Beat type: {beat_type}. Narration beat: {beat['text']}. "
            f"Visual direction: {visual_direction}. "
            "Style: premium true crime documentary, ultra-realistic, photographic quality, "
            "8K detail level, sharp focus especially on faces, dramatic side lighting, "
            "deep blacks, rich shadow detail, cinematic depth of field, strong composition, "
            "dark moody color grading, accurate anatomy especially skin hands and face, "
            "no text, no logos, no collage, no subtitles, no watermarks, no UI elements. "
            "Keep the subject identity and appearance strictly consistent across all scenes."
        )
        prompts.append(
            {
                "scene": index,
                "beat_type": beat_type,
                "subject": subject,
                "narration_text": beat["text"],
                "start": round(beat.get("start", 0.0), 3),
                "end": round(beat.get("end", 0.0), 3),
                "prompt": prompt,
                "filename": f"scene_{index:02d}.png",
            }
        )
    return prompts


def build_thumbnail_prompt(topic: str, script: str) -> dict:
    first_line = script.split("\n")[0].strip()
    prompt = (
        f"Create a cinematic YouTube thumbnail image about '{topic}'. "
        f"Narrative base: {first_line}. "
        "16:9 format, intense close-up or a very clear iconic scene, high contrast, "
        "clean composition, strong visual impact, dark atmosphere, deep red accents, "
        "expressive faces if present, no text, no logos, no subtitles, no collage."
    )
    return {
        "prompt": prompt,
        "filename": "thumbnail.png",
    }


def save_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_or_create_prompts(
    script_path: Path,
    timestamps_path: Path,
    prompts_path: Path,
    thumb_prompt_path: Path,
    topic: str,
    scene_count: int,
) -> tuple[list[dict], dict]:
    script = normalize_script(script_path.read_text(encoding="utf-8"))
    timestamps = load_timestamps(timestamps_path)

    prompts = build_scene_prompts(topic, script, timestamps, scene_count)
    save_json(prompts_path, prompts)

    if thumb_prompt_path.is_file():
        thumb_prompt = json.loads(thumb_prompt_path.read_text(encoding="utf-8"))
    else:
        thumb_prompt = build_thumbnail_prompt(topic, script)
        save_json(thumb_prompt_path, thumb_prompt)

    return prompts, thumb_prompt


def generate_image(prompt: str, model: str, aspect_ratio: str = "16:9") -> tuple[bytes, str]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY for Gemini image generation.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
        },
    }

    last_error = None
    data = None
    for attempt in range(1, MAX_RETRIES + 1):
        response = requests.post(
            url,
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,
        )
        if response.ok:
            data = response.json()
            break

        last_error = f"status={response.status_code} body={response.text[:500]}"
        if response.status_code == 429 and attempt < MAX_RETRIES:
            wait_seconds = attempt * 8
            print(f"Gemini image rate-limited. Retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)
            continue
        response.raise_for_status()

    if data is None:
        raise RuntimeError(f"Failed to generate image with Gemini: {last_error}")

    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline_data = part.get("inline_data")
            if inline_data and inline_data.get("data"):
                return base64.b64decode(inline_data["data"]), inline_data.get("mime_type", "image/png")

    raise RuntimeError(f"Gemini returned no image. Response: {json.dumps(data)[:800]}")


def extension_for_mime(mime_type: str) -> str:
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/webp":
        return ".webp"
    return ".png"


def ensure_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def write_image(target_without_suffix: Path, image_bytes: bytes, mime_type: str) -> Path:
    target_path = target_without_suffix.with_suffix(extension_for_mime(mime_type))
    target_path.write_bytes(image_bytes)
    return target_path


def clear_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.iterdir():
        if path.is_file():
            try:
                path.unlink()
            except PermissionError:
                continue


def generate_scene_images(prompts: list[dict], output_dir: Path, model: str) -> list[Path]:
    clear_output_dir(output_dir)
    generated_paths: list[Path] = []

    for prompt_info in prompts:
        print(f"Generating image {prompt_info['scene']}/{len(prompts)}...")
        try:
            image_bytes, mime_type = generate_image(prompt_info["prompt"], model, aspect_ratio="16:9")
        except Exception as exc:
            print(f"Scene {prompt_info['scene']} failed: {exc}")
            continue
        target_base = output_dir / Path(prompt_info["filename"]).stem
        target_path = write_image(target_base, image_bytes, mime_type)
        generated_paths.append(target_path)
        print(f"Saved: {target_path}")

    return generated_paths


def generate_thumbnail(thumb_prompt: dict, thumbnail_path: Path, model: str) -> Path | None:
    print("Generating AI thumbnail...")
    try:
        image_bytes, mime_type = generate_image(thumb_prompt["prompt"], model, aspect_ratio="16:9")
    except Exception as exc:
        print(f"Thumbnail generation failed: {exc}")
        return None

    target_base = thumbnail_path.with_suffix("")
    target_path = write_image(target_base, image_bytes, mime_type)
    print(f"Thumbnail saved: {target_path}")
    return target_path


def main() -> int:
    args = parse_args()
    script_path = Path(args.script)
    timestamps_path = Path(args.timestamps)
    prompts_path = Path(args.prompts)
    thumb_prompt_path = Path(args.thumb_prompt)
    output_dir = Path(args.output_dir)
    thumbnail_path = Path(args.thumbnail)

    if not script_path.is_file():
        raise FileNotFoundError(f"Script not found: {script_path}")

    topic = args.topic.strip() or script_path.stem.replace("_", " ")
    prompts, thumb_prompt = load_or_create_prompts(
        script_path,
        timestamps_path,
        prompts_path,
        thumb_prompt_path,
        topic,
        max(args.scene_count, 1),
    )
    if args.prompts_only:
        generated = []
        thumbnail = None
    else:
        generated = generate_scene_images(prompts, output_dir, args.model)
        thumbnail = generate_thumbnail(thumb_prompt, thumbnail_path, args.model)
    print(f"Images ready: {len(generated)}")
    print(f"Thumbnail ready: {thumbnail if thumbnail else 'not generated'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
