import argparse
import json
import os
import re
import textwrap
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCRIPT = BASE_DIR / "guion.txt"
DEFAULT_METADATA = BASE_DIR / "metadata.json"
DEFAULT_OUTPUT = BASE_DIR / "creatomate_slideshow.mp4"
DEFAULT_FEED = BASE_DIR / "creatomate_slideshow_payload.json"
API_BASE = "https://api.creatomate.com/v2"
API_KEY = os.getenv("CREATOMATE_API_KEY", "").strip()
TEMPLATE_ID = os.getenv("CREATOMATE_SLIDESHOW_TEMPLATE_ID", "").strip()

DEFAULT_IMAGE_URLS = [
    "https://creatomate.com/files/assets/5bc5ed6f-26e6-4c3a-8d03-1b169dc7f983.jpg",
    "https://creatomate.com/files/assets/63dfc7e7-8621-4779-b471-e4098783eaa2.jpg",
    "https://creatomate.com/files/assets/5e62bfc9-060a-4a27-aba0-aecdc49215b7.jpg",
    "https://creatomate.com/files/assets/0ae5625b-8c8d-498c-9f35-fb50797efbd1.jpg",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render the Image Slideshow w/ Intro and Outro Creatomate template.")
    parser.add_argument("--topic", default="", help="Video topic.")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--payload", default=str(DEFAULT_FEED))
    parser.add_argument("--main-image-url", default="")
    parser.add_argument("--slide-1-url", default="")
    parser.add_argument("--slide-2-url", default="")
    parser.add_argument("--slide-3-url", default="")
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()


def load_metadata(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part.strip() for part in parts if part.strip()]


def shorten(value: str, width: int) -> str:
    value = " ".join(value.split())
    return textwrap.shorten(value, width=width, placeholder="...")


def wrap_upper(value: str, width: int) -> str:
    return textwrap.fill(shorten(value.upper(), width=width * 3), width=width)


def build_copy(topic: str, metadata: dict, script: str) -> dict[str, str]:
    title = str(metadata.get("title") or topic or "Crime Files").strip()
    sentences = split_sentences(script)
    while len(sentences) < 5:
        sentences.append("")

    tagline = "TRUE CRIME FILES"
    start_text = shorten(sentences[0] or f"The hidden truth behind {topic}.", 60)
    slide_1_text = shorten(sentences[1] or f"The case of {topic} shocked the public.", 56)
    slide_2_text = shorten(sentences[2] or "A trail of fear, manipulation, and violence followed.", 56)
    final_text = shorten(
        "Subscribe for more criminal cases, darker stories, and unsettling real investigations.",
        64,
    )

    return {
        "Tagline.text": tagline,
        "Title.text": wrap_upper(title, 18),
        "Start-Text.text": start_text,
        "Slide-1-Text.text": slide_1_text,
        "Slide-2-Text.text": shorten(slide_2_text, 56),
        "Slide-3-Text.text": shorten(sentences[3] or "The final details still disturb investigators today.", 56),
        "Final-Text.text": wrap_upper(final_text, 18),
    }


def build_image_sources(args: argparse.Namespace) -> dict[str, str]:
    urls = [
        args.main_image_url.strip() or DEFAULT_IMAGE_URLS[0],
        args.slide_1_url.strip() or DEFAULT_IMAGE_URLS[1],
        args.slide_2_url.strip() or DEFAULT_IMAGE_URLS[2],
        args.slide_3_url.strip() or DEFAULT_IMAGE_URLS[3],
    ]
    return {
        "Main-Image.source": urls[0],
        "Slide-1-Image.source": urls[1],
        "Slide-2-Image.source": urls[2],
        "Slide-3-Image.source": urls[3],
    }


def headers() -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("Missing CREATOMATE_API_KEY.")
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def create_render(payload: dict) -> dict:
    response = requests.post(
        f"{API_BASE}/renders",
        headers=headers(),
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        return data[0]
    return data


def get_render(render_id: str) -> dict:
    response = requests.get(
        f"{API_BASE}/renders/{render_id}",
        headers=headers(),
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def wait_for_render(render_id: str, timeout_seconds: int = 600) -> dict:
    started = time.time()
    while True:
        render = get_render(render_id)
        status = render.get("status")
        if status == "succeeded":
            return render
        if status == "failed":
            raise RuntimeError(f"Creatomate slideshow render failed: {render}")
        if time.time() - started > timeout_seconds:
            raise TimeoutError("Creatomate slideshow render timed out.")
        print(f"Creatomate slideshow status: {status}")
        time.sleep(6)


def download_file(url: str, output_path: Path) -> None:
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    output_path.write_bytes(response.content)


def main() -> int:
    args = parse_args()
    if not TEMPLATE_ID:
        raise RuntimeError("Missing CREATOMATE_SLIDESHOW_TEMPLATE_ID.")

    script = read_text(Path(args.script))
    metadata = load_metadata(Path(args.metadata))
    topic = args.topic.strip() or metadata.get("title", "") or "Crime Files"

    modifications = {}
    modifications.update(build_image_sources(args))
    modifications.update(build_copy(topic, metadata, script))

    payload = {
        "template_id": TEMPLATE_ID,
        "modifications": modifications,
    }
    Path(args.payload).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("Submitting Creatomate slideshow render...")
    render = create_render(payload)
    final_render = wait_for_render(render["id"])
    output_url = final_render.get("url")
    if not output_url:
        raise RuntimeError(f"Creatomate slideshow succeeded but returned no URL: {final_render}")

    download_file(output_url, Path(args.output))
    print(f"Creatomate slideshow saved to: {Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
