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
DEFAULT_PAYLOAD = BASE_DIR / "json2video_payload.json"
DEFAULT_OUTPUT_URL = BASE_DIR / "json2video_output_url.txt"
API_KEY = os.getenv("JSON2VIDEO_API_KEY", "").strip()
API_BASE = "https://api.json2video.com/v2"
DEFAULT_VOICE = "en-US-GuyNeural"

IMAGE_URLS = [
    "https://cdn.json2video.com/assets/images/london-01.jpg",
    "https://cdn.json2video.com/assets/images/london-02.jpg",
    "https://cdn.json2video.com/assets/images/london-03.jpg",
    "https://assets.json2video.com/assets/images/space-apollo11-01.jpg",
    "https://assets.json2video.com/assets/images/man-01.jpg",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a test video with JSON2Video.")
    parser.add_argument("--topic", default="", help="Video topic.")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--payload", default=str(DEFAULT_PAYLOAD))
    parser.add_argument("--output-url-file", default=str(DEFAULT_OUTPUT_URL))
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


def split_sentences(script: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", script.strip())
    return [part.strip() for part in parts if part.strip()]


def shorten(value: str, width: int) -> str:
    return textwrap.shorten(" ".join(value.split()), width=width, placeholder="...")


def wrap_text(value: str, width: int) -> str:
    return textwrap.fill(" ".join(value.split()), width=width)


def scene_text(sentences: list[str], index: int, fallback: str, width: int) -> str:
    if index < len(sentences) and sentences[index]:
        return shorten(sentences[index], width)
    return fallback


def build_payload(topic: str, title: str, script: str) -> dict:
    sentences = split_sentences(script)
    while len(sentences) < 8:
        sentences.append("")

    opener = scene_text(sentences, 0, f"The hidden truth behind {topic}.", 140)
    setup = scene_text(sentences, 1, f"The case of {topic} shocked the country.", 180)
    escalation = scene_text(sentences, 2, "The investigation only got darker from there.", 180)
    profile = scene_text(sentences, 3, "The killer hid in plain sight and weaponized trust.", 170)
    investigation = scene_text(sentences, 4, "Police chased patterns that kept slipping across state lines.", 170)
    aftermath = scene_text(sentences, 5, "The final crimes left a scar that still shapes the case today.", 180)
    reflection = scene_text(sentences, 6, "Some details still feel impossible to forget.", 150)
    closer = scene_text(sentences, 7, "Subscribe for more disturbing real cases.", 120)

    return {
        "comment": "JSON2Video premium render for Crime Files",
        "resolution": "full-hd",
        "quality": "high",
        "scenes": [
            {
                "comment": "Hook scene",
                "duration": 4.5,
                "background-color": "#07080d",
                "elements": [
                    {
                        "type": "image",
                        "src": IMAGE_URLS[0],
                        "zoom": 6,
                        "pan": "right",
                    },
                    {
                        "type": "text",
                        "text": "CRIME FILES",
                        "x": 225,
                        "y": 105,
                        "width": 360,
                        "height": 64,
                        "font": "Montserrat",
                        "font-size": 28,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "background-color": "#b5141add",
                        "padding-x": 18,
                        "padding-y": 10,
                    },
                    {
                        "type": "text",
                        "text": wrap_text(title.upper(), 18),
                        "x": 640,
                        "y": 270,
                        "width": 1080,
                        "height": 220,
                        "font": "Montserrat",
                        "font-size": 60,
                        "font-weight": "700",
                        "text-align": "center",
                        "color": "#ffffff",
                    },
                    {
                        "type": "text",
                        "text": wrap_text(opener, 34),
                        "x": 640,
                        "y": 560,
                        "width": 1040,
                        "height": 150,
                        "font": "Montserrat",
                        "font-size": 32,
                        "font-weight": "600",
                        "text-align": "center",
                        "color": "#ffffff",
                        "background-color": "#00000088",
                    },
                    {
                        "type": "voice",
                        "voice": DEFAULT_VOICE,
                        "text": f"<fast>{opener}</fast>",
                        "start": 0.25,
                    },
                ],
            },
            {
                "comment": "Prologue scene",
                "duration": 6,
                "background-color": "#090b10",
                "elements": [
                    {
                        "type": "image",
                        "src": IMAGE_URLS[1],
                        "zoom": 4,
                        "pan": "left",
                    },
                    {
                        "type": "text",
                        "text": "THE SETUP",
                        "x": 190,
                        "y": 108,
                        "width": 280,
                        "height": 56,
                        "font": "Montserrat",
                        "font-size": 24,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "background-color": "#b5141add",
                    },
                    {
                        "type": "text",
                        "text": wrap_text(setup, 30),
                        "x": 170,
                        "y": 450,
                        "width": 940,
                        "height": 180,
                        "font": "Montserrat",
                        "font-size": 44,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "background-color": "#00000088",
                    },
                    {
                        "type": "voice",
                        "voice": DEFAULT_VOICE,
                        "text": setup,
                        "start": 0.4,
                    },
                ],
            },
            {
                "comment": "Escalation scene",
                "duration": 6,
                "background-color": "#0a0b11",
                "elements": [
                    {
                        "type": "image",
                        "src": IMAGE_URLS[2],
                        "zoom": 5,
                        "pan": "top",
                    },
                    {
                        "type": "text",
                        "text": "THE KILL PATTERN",
                        "x": 1010,
                        "y": 96,
                        "width": 360,
                        "height": 58,
                        "font": "Montserrat",
                        "font-size": 24,
                        "font-weight": "700",
                        "text-align": "center",
                        "color": "#ffffff",
                        "background-color": "#b5141add",
                    },
                    {
                        "type": "text",
                        "text": wrap_text(escalation, 28),
                        "x": 985,
                        "y": 472,
                        "width": 900,
                        "height": 180,
                        "font": "Montserrat",
                        "font-size": 42,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "text-align": "right",
                        "background-color": "#00000088",
                    },
                    {
                        "type": "voice",
                        "voice": DEFAULT_VOICE,
                        "text": escalation,
                        "start": 0.4,
                    },
                ],
            },
            {
                "comment": "Profile scene",
                "duration": 5.5,
                "background-color": "#08090d",
                "elements": [
                    {
                        "type": "image",
                        "src": IMAGE_URLS[2],
                        "zoom": 4,
                        "pan": "bottom",
                    },
                    {
                        "type": "text",
                        "text": "WHO HE WAS",
                        "x": 220,
                        "y": 102,
                        "width": 300,
                        "height": 56,
                        "font": "Montserrat",
                        "font-size": 24,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "background-color": "#b5141add",
                    },
                    {
                        "type": "text",
                        "text": wrap_text(profile, 30),
                        "x": 210,
                        "y": 450,
                        "width": 960,
                        "height": 170,
                        "font": "Montserrat",
                        "font-size": 42,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "background-color": "#00000099",
                    },
                    {
                        "type": "voice",
                        "voice": DEFAULT_VOICE,
                        "text": profile,
                        "start": 0.4,
                    },
                ],
            },
            {
                "comment": "Investigation scene",
                "duration": 6,
                "background-color": "#090a10",
                "elements": [
                    {
                        "type": "image",
                        "src": IMAGE_URLS[3],
                        "zoom": 4,
                        "pan": "right",
                    },
                    {
                        "type": "text",
                        "text": "THE MANHUNT",
                        "x": 1020,
                        "y": 98,
                        "width": 330,
                        "height": 56,
                        "font": "Montserrat",
                        "font-size": 24,
                        "font-weight": "700",
                        "text-align": "center",
                        "color": "#ffffff",
                        "background-color": "#b5141add",
                    },
                    {
                        "type": "text",
                        "text": wrap_text(investigation, 28),
                        "x": 980,
                        "y": 470,
                        "width": 920,
                        "height": 180,
                        "font": "Montserrat",
                        "font-size": 40,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "text-align": "right",
                        "background-color": "#00000099",
                    },
                    {
                        "type": "voice",
                        "voice": DEFAULT_VOICE,
                        "text": investigation,
                        "start": 0.4,
                    },
                ],
            },
            {
                "comment": "Aftermath and CTA scene",
                "duration": 7,
                "background-color": "#05060b",
                "elements": [
                    {
                        "type": "image",
                        "src": IMAGE_URLS[4],
                        "zoom": 5,
                        "pan": "left",
                    },
                    {
                        "type": "text",
                        "text": "THE AFTERMATH",
                        "x": 220,
                        "y": 98,
                        "width": 340,
                        "height": 56,
                        "font": "Montserrat",
                        "font-size": 24,
                        "font-weight": "700",
                        "color": "#ffffff",
                        "background-color": "#b5141add",
                    },
                    {
                        "type": "text",
                        "text": wrap_text(aftermath, 30),
                        "x": 640,
                        "y": 230,
                        "width": 1120,
                        "height": 180,
                        "font": "Montserrat",
                        "font-size": 42,
                        "font-weight": "700",
                        "text-align": "center",
                        "color": "#ffffff",
                        "background-color": "#00000088",
                    },
                    {
                        "type": "text",
                        "text": wrap_text(reflection, 38),
                        "x": 640,
                        "y": 470,
                        "width": 980,
                        "height": 100,
                        "font": "Montserrat",
                        "font-size": 28,
                        "font-weight": "600",
                        "text-align": "center",
                        "color": "#ffffff",
                    },
                    {
                        "type": "text",
                        "text": "SUBSCRIBE FOR MORE TRUE CRIME FILES",
                        "x": 640,
                        "y": 620,
                        "width": 940,
                        "height": 68,
                        "font": "Montserrat",
                        "font-size": 24,
                        "font-weight": "700",
                        "text-align": "center",
                        "color": "#ffffff",
                        "background-color": "#c31f23dd",
                    },
                    {
                        "type": "voice",
                        "voice": DEFAULT_VOICE,
                        "text": f"{aftermath} {reflection} <fast>{closer}</fast>",
                        "start": 0.4,
                    },
                ],
            },
        ],
    }


def headers() -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("Missing JSON2VIDEO_API_KEY.")
    return {
        "x-api-key": API_KEY,
        "Content-Type": "application/json",
    }


def create_movie(payload: dict) -> dict:
    response = requests.post(
        f"{API_BASE}/movies",
        headers=headers(),
        json=payload,
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def get_movie(project_id: str) -> dict:
    response = requests.get(
        f"{API_BASE}/movies",
        headers=headers(),
        params={"project": project_id},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict) and isinstance(data.get("movie"), dict):
        return data["movie"]
    if isinstance(data, list):
        return data[0]
    return data


def wait_for_movie(project_id: str, timeout_seconds: int = 600) -> dict:
    started = time.time()
    while True:
        movie = get_movie(project_id)
        status = movie.get("status")
        if status in {"done", "completed"}:
            return movie
        if status in {"failed", "error"}:
            raise RuntimeError(f"JSON2Video render failed: {movie}")
        if time.time() - started > timeout_seconds:
            raise TimeoutError("JSON2Video render timed out.")
        print(f"JSON2Video status: {status}")
        time.sleep(6)


def main() -> int:
    args = parse_args()
    metadata = load_metadata(Path(args.metadata))
    script = read_text(Path(args.script))
    topic = args.topic.strip() or metadata.get("title", "") or "Crime Files"
    title = str(metadata.get("title") or topic).strip()

    payload = build_payload(topic, title, script)
    Path(args.payload).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("Submitting JSON2Video render...")
    created = create_movie(payload)
    project_id = created.get("project")
    if not project_id:
        raise RuntimeError(f"JSON2Video returned no project id: {created}")

    movie = wait_for_movie(project_id)
    movie_url = movie.get("movie_url") or movie.get("url") or ""
    Path(args.output_url_file).write_text(movie_url, encoding="utf-8")
    print(f"JSON2Video movie URL: {movie_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
