import argparse
import base64
import io
import json
import mimetypes
import os
from pathlib import Path
from urllib.request import Request, urlopen, urlretrieve

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFilter
from runwayml import RunwayML, TaskFailedError


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCRIPT = BASE_DIR / "short_script.txt"
DEFAULT_PROMPT_IMAGE = BASE_DIR / "runway_prompt.png"
DEFAULT_OUTPUT = BASE_DIR / "runway_clip.mp4"
DEFAULT_RATIO = "720:1280"
DEFAULT_DURATION = 10
DEFAULT_MODEL = "gen4_turbo"
FALLBACK_KEY_FILE = Path(r"C:\Users\yoeld\Desktop\APi_Runway.txt")
MODEL_MAX_DURATION = {
    "gen3a_turbo": 10,
    "gen4_turbo": 10,
    "gen4": 10,
}
WIKIMEDIA_UA = "youtube-bot/1.0 (local automation test)"

load_dotenv()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a premium motion clip with Runway.")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT))
    parser.add_argument("--topic", required=True)
    parser.add_argument("--prompt-image", default=str(DEFAULT_PROMPT_IMAGE))
    parser.add_argument("--prompt-text", default="", help="Override the generated prompt text.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--ratio", default=DEFAULT_RATIO)
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    return parser.parse_args()


def load_api_key() -> str:
    env_key = os.getenv("RUNWAYML_API_SECRET", "").strip()
    if env_key:
        return env_key
    if FALLBACK_KEY_FILE.is_file():
        return FALLBACK_KEY_FILE.read_text(encoding="utf-8").strip()
    raise RuntimeError("Runway API key not found. Set RUNWAYML_API_SECRET or place it in APi_Runway.txt.")


def normalize_script(text: str) -> str:
    return " ".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def build_prompt(topic: str, script: str) -> str:
    lower = topic.lower()
    if "aileen" in lower or "wuornos" in lower:
        return (
            "A lonely Florida highway at night, humid air, distant motel lights, "
            "subtle camera drift, tense documentary atmosphere, realistic, cinematic lighting, readable exposure, no text."
        )
    if "zodiac" in lower:
        return (
            "A dark Northern California roadside at night, police search atmosphere, distant car lights, "
            "slow cinematic movement, investigative documentary mood, realistic, readable exposure, no text."
        )
    if "bundy" in lower:
        return (
            "A quiet suburban night with an ominous parked car, gentle camera push, "
            "tense documentary atmosphere, realistic, cinematic lighting, readable exposure, no text."
        )
    if "ramirez" in lower or "night stalker" in lower:
        return (
            "A shadowy Los Angeles street at night, open window, slow moving camera, "
            "suspenseful documentary tone, realistic, cinematic lighting, readable exposure, no text."
        )
    return (
        f"A tense documentary-style environment inspired by {topic}, "
        "dark cinematic mood, subtle motion, realistic, atmospheric, readable exposure, no text, no gore."
    )


def image_to_data_uri(image_path: Path) -> str:
    content_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:{content_type};base64,{encoded}"


def _wikimedia_topic_query(topic: str) -> str:
    lower = topic.lower()
    if "zodiac" in lower:
        return "Zodiac Killer"
    if "bundy" in lower:
        return "Ted Bundy"
    if "ramirez" in lower or "night stalker" in lower:
        return "Richard Ramirez"
    if "aileen" in lower or "wuornos" in lower:
        return "Aileen Wuornos"
    if "dahmer" in lower:
        return "Jeffrey Dahmer"
    if "btk" in lower:
        return "Dennis Rader BTK"
    if "gacy" in lower:
        return "John Wayne Gacy"
    if "manson" in lower:
        return "Charles Manson"
    return topic.split("|")[0].strip()


def _try_wikimedia_image(topic: str, output_path: Path) -> bool:
    import urllib.parse
    query = _wikimedia_topic_query(topic)
    params = urllib.parse.urlencode({
        "action": "query", "format": "json",
        "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 8,
        "prop": "imageinfo", "iiprop": "url",
    })
    try:
        req = Request(
            f"https://commons.wikimedia.org/w/api.php?{params}",
            headers={"User-Agent": WIKIMEDIA_UA},
        )
        with urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            title = str(page.get("title", "")).lower()
            if not any(ext in title for ext in (".jpg", ".jpeg", ".png")):
                continue
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            url = infos[0].get("url", "")
            if not url:
                continue
            img_req = Request(url, headers={"User-Agent": WIKIMEDIA_UA})
            with urlopen(img_req, timeout=15) as resp:
                img_bytes = resp.read()
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img = img.resize((720, 1280), Image.LANCZOS)
            img.save(output_path)
            print(f"Runway reference image: Wikimedia ({title})")
            return True
    except Exception as exc:
        print(f"Wikimedia fetch failed, using synthetic fallback: {exc}")
    return False


def create_prompt_image(topic: str, output_path: Path) -> Path:
    # Prefer a real image from generated_images/ if available
    gen_dir = BASE_DIR / "generated_images"
    if gen_dir.is_dir():
        for candidate in sorted(gen_dir.iterdir()):
            if candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                try:
                    img = Image.open(candidate).convert("RGB")
                    img = img.resize((720, 1280), Image.LANCZOS)
                    img.save(output_path)
                    print(f"Runway reference image: {candidate.name}")
                    return output_path
                except Exception:
                    continue

    # Try Wikimedia as second option
    if _try_wikimedia_image(topic, output_path):
        return output_path

    # Synthetic fallback — dark cinematic gradient
    image = Image.new("RGB", (720, 1280), (18, 18, 24))
    draw = ImageDraw.Draw(image)
    for y in range(1280):
        shade = int(18 + 22 * (y / 1280))
        draw.line((0, y, 720, y), fill=(shade, shade, shade + 10))
    draw.ellipse((-120, 120, 420, 760), fill=(92, 26, 30))
    draw.ellipse((260, 760, 860, 1380), fill=(28, 36, 58))
    image = image.filter(ImageFilter.GaussianBlur(1.5))
    image.save(output_path)
    return output_path


def main() -> int:
    args = parse_args()
    script_path = Path(args.script)
    prompt_image_path = Path(args.prompt_image)
    if not script_path.is_file():
        raise FileNotFoundError(f"Script not found: {script_path}")
    if prompt_image_path == DEFAULT_PROMPT_IMAGE or not prompt_image_path.is_file():
        prompt_image_path = create_prompt_image(args.topic, prompt_image_path)

    api_key = load_api_key()
    os.environ["RUNWAYML_API_SECRET"] = api_key
    script = normalize_script(script_path.read_text(encoding="utf-8"))
    prompt = args.prompt_text.strip() or build_prompt(args.topic, script)
    prompt_image = image_to_data_uri(prompt_image_path)
    max_duration = MODEL_MAX_DURATION.get(args.model, args.duration)
    duration = min(args.duration, max_duration)

    client = RunwayML(api_key=api_key)
    try:
        task = client.image_to_video.create(
            model=args.model,
            prompt_image=prompt_image,
            prompt_text=prompt,
            ratio=args.ratio,
            duration=duration,
        ).wait_for_task_output()
    except TaskFailedError as exc:
        raise RuntimeError(f"Runway task failed: {exc.task_details}") from exc

    output = task.output
    if not output:
        raise RuntimeError("Runway returned no output URL.")

    video_url = output[0]
    target = Path(args.output)
    urlretrieve(video_url, target)
    print(f"Runway clip saved to: {target}")
    print(f"Source URL: {video_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
