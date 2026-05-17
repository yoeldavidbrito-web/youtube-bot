import argparse
import base64
import hashlib
import hmac
import io
import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen, urlretrieve

import requests
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "kling_clip.mp4"
API_BASE = "https://api.klingai.com"
POLL_INTERVAL = 10
MAX_WAIT = 600

WIKIMEDIA_UA = "youtube-bot/1.0 (kling renderer)"

# Wikimedia portrait photos per criminal for image-to-video
TOPIC_PORTRAIT_QUERIES = {
    "dahmer": "Jeffrey Dahmer",
    "bundy": "Ted Bundy",
    "zodiac": "Zodiac Killer composite sketch",
    "ramirez": "Richard Ramirez mugshot",
    "btk": "Dennis Rader BTK",
    "gacy": "John Wayne Gacy",
    "manson": "Charles Manson",
    "aileen": "Aileen Wuornos",
    "wuornos": "Aileen Wuornos",
}

# What motion/expression to apply on the portrait
TOPIC_ANIMATE_PROMPTS = {
    "dahmer": (
        "Slow subtle head turn, cold expressionless face, hollow eyes, slight unsettling stillness, "
        "clinical detachment, dim institutional lighting, no sudden movement, ominous documentary realism"
    ),
    "bundy": (
        "Slow charming smile that doesn't reach the eyes, slight head tilt, "
        "deceptively pleasant expression hiding darkness, courtroom lighting, unsettling calm"
    ),
    "zodiac": (
        "Composite sketch coming to life, slow blink, calculating gaze scanning the frame, "
        "dark hat casting shadow over eyes, ominous stillness, cold documentary light"
    ),
    "ramirez": (
        "Slow cold stare directly into camera, slight jaw tension, unsettling intensity, "
        "dark shadows, courtroom atmosphere, chilling eye contact"
    ),
}

GENERIC_ANIMATE_PROMPT = (
    "Slow subtle head movement, cold calculating expression, ominous stillness, "
    "documentary lighting, haunting presence, no sudden motion"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Animate a criminal portrait with Kling AI image-to-video.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--duration", type=int, default=5, choices=[5, 10])
    parser.add_argument("--image", default="", help="Local image path to animate (auto-fetches from Wikimedia if empty).")
    parser.add_argument("--prompt-text", default="", help="Override the animation prompt.")
    return parser.parse_args()


def load_credentials() -> tuple[str, str]:
    access_key = os.getenv("KLING_ACCESS_KEY", "").strip()
    secret_key = os.getenv("KLING_SECRET_KEY", "").strip()
    if not access_key or not secret_key:
        raise RuntimeError(
            "KLING_ACCESS_KEY and KLING_SECRET_KEY not found. "
            "Get them at https://klingai.com/dev and add to your .env file."
        )
    return access_key, secret_key


def build_jwt(access_key: str, secret_key: str) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    now = int(time.time())
    payload = base64.urlsafe_b64encode(
        json.dumps({"iss": access_key, "exp": now + 1800, "nbf": now - 5}).encode()
    ).rstrip(b"=").decode()
    sig_input = f"{header}.{payload}".encode()
    signature = base64.urlsafe_b64encode(
        hmac.new(secret_key.encode(), sig_input, hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    return f"{header}.{payload}.{signature}"


def fetch_wikimedia_portrait(topic: str) -> Image.Image | None:
    import urllib.parse
    lower = topic.lower()
    query = next((v for k, v in TOPIC_PORTRAIT_QUERIES.items() if k in lower), topic)
    params = urllib.parse.urlencode({
        "action": "query", "format": "json",
        "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 10,
        "prop": "imageinfo", "iiprop": "url|size",
    })
    try:
        req = Request(
            f"https://commons.wikimedia.org/w/api.php?{params}",
            headers={"User-Agent": WIKIMEDIA_UA},
        )
        with urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {})
        best_url, best_width = "", 0
        for page in pages.values():
            title = str(page.get("title", "")).lower()
            if not any(ext in title for ext in (".jpg", ".jpeg", ".png")):
                continue
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            url = infos[0].get("url", "")
            width = infos[0].get("width", 0)
            if url and width > best_width:
                best_url, best_width = url, width
        if not best_url:
            return None
        img_req = Request(best_url, headers={"User-Agent": WIKIMEDIA_UA})
        with urlopen(img_req, timeout=15) as resp:
            return Image.open(io.BytesIO(resp.read())).convert("RGB")
    except Exception as exc:
        print(f"Wikimedia portrait fetch failed: {exc}")
        return None


def image_to_base64(img: Image.Image) -> str:
    img = img.resize((768, 1024), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return base64.b64encode(buf.getvalue()).decode()


def submit_image_to_video(jwt: str, image_b64: str, prompt: str, duration: int) -> str:
    resp = requests.post(
        f"{API_BASE}/v1/videos/image2video",
        headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
        json={
            "model_name": "kling-v1.6",
            "image": image_b64,
            "prompt": prompt,
            "duration": str(duration),
            "cfg_scale": 0.5,
            "mode": "std",
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get("data", {}).get("task_id") or data.get("task_id")
    if not task_id:
        raise RuntimeError(f"Kling returned no task_id: {data}")
    print(f"Kling task submitted: {task_id}")
    return task_id


def wait_for_kling(jwt: str, task_id: str) -> str:
    print("Waiting for Kling AI", end="", flush=True)
    elapsed = 0
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        resp = requests.get(
            f"{API_BASE}/v1/videos/image2video/{task_id}",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("data", resp.json())
        status = data.get("task_status", "")
        print(".", end="", flush=True)
        if status == "succeed":
            works = data.get("task_result", {}).get("videos", [])
            if works:
                url = works[0].get("url", "")
                print(f"\nKling clip ready: {url}")
                return url
            raise RuntimeError("Kling returned no video URL in result.")
        if status == "failed":
            raise RuntimeError(f"Kling task failed: {data.get('task_status_msg', data)}")
    raise TimeoutError(f"Kling did not finish in {MAX_WAIT}s.")


def main() -> int:
    args = parse_args()
    access_key, secret_key = load_credentials()
    jwt = build_jwt(access_key, secret_key)

    # Resolve image
    if args.image and Path(args.image).is_file():
        img = Image.open(args.image).convert("RGB")
        print(f"Using local image: {args.image}")
    else:
        print(f"Fetching portrait for: {args.topic}")
        img = fetch_wikimedia_portrait(args.topic)
        if img is None:
            raise RuntimeError("Could not fetch a portrait image. Pass --image <path> manually.")
        print("Portrait fetched from Wikimedia.")

    image_b64 = image_to_base64(img)
    lower = args.topic.lower()
    prompt = args.prompt_text.strip() or next(
        (v for k, v in TOPIC_ANIMATE_PROMPTS.items() if k in lower),
        GENERIC_ANIMATE_PROMPT,
    )
    print(f"Animation prompt: {prompt[:100]}...")

    task_id = submit_image_to_video(jwt, image_b64, prompt, args.duration)
    video_url = wait_for_kling(jwt, task_id)

    output = Path(args.output)
    urlretrieve(video_url, output)
    print(f"Kling clip saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
