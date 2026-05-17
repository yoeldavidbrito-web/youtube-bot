import argparse
import json
import os
import textwrap
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCRIPT = BASE_DIR / "guion.txt"
DEFAULT_METADATA = BASE_DIR / "metadata.json"
DEFAULT_OUTPUT = BASE_DIR / "creatomate_intro.mp4"
API_BASE = "https://api.creatomate.com/v2"
TEMPLATE_ID = os.getenv("CREATOMATE_TEMPLATE_ID", "").strip()
API_KEY = os.getenv("CREATOMATE_API_KEY", "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a premium intro clip with Creatomate.")
    parser.add_argument("--topic", default="", help="Video topic.")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--video-source", default="", help="Optional public video URL for the template background.")
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


def first_sentence(script: str) -> str:
    for splitter in (". ", "? ", "! "):
        if splitter in script:
            return script.split(splitter, 1)[0].strip(" .?!")
    return script[:120].strip()


def build_text_lines(topic: str, metadata: dict, script: str) -> tuple[str, str]:
    title = str(metadata.get("title") or topic or "Crime Files").strip()
    title = title.replace("|", "").replace("  ", " ")
    hook = first_sentence(script)
    hook = hook[:90].strip()

    line_1 = textwrap.shorten(title, width=28, placeholder="...")
    line_2 = textwrap.fill(textwrap.shorten(hook, width=56, placeholder="..."), width=16)
    return line_1, line_2


def creatomate_headers() -> dict[str, str]:
    if not API_KEY:
        raise RuntimeError("Missing CREATOMATE_API_KEY.")
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }


def create_render(template_id: str, modifications: dict) -> dict:
    payload = {
        "template_id": template_id,
        "modifications": modifications,
    }
    response = requests.post(
        f"{API_BASE}/renders",
        headers=creatomate_headers(),
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
        headers=creatomate_headers(),
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
            raise RuntimeError(f"Creatomate render failed: {render}")
        if time.time() - started > timeout_seconds:
            raise TimeoutError(f"Creatomate render timed out after {timeout_seconds}s")
        print(f"Creatomate render status: {status}")
        time.sleep(6)


def download_file(url: str, output_path: Path) -> None:
    response = requests.get(url, timeout=300)
    response.raise_for_status()
    output_path.write_bytes(response.content)


def main() -> int:
    args = parse_args()
    if not TEMPLATE_ID:
        raise RuntimeError("Missing CREATOMATE_TEMPLATE_ID.")

    script = read_text(Path(args.script))
    metadata = load_metadata(Path(args.metadata))
    topic = args.topic.strip() or metadata.get("title", "") or "Crime Files"
    line_1, line_2 = build_text_lines(topic, metadata, script)

    modifications = {
        "Text-1.text": line_1,
        "Text-2.text": line_2,
    }
    if args.video_source.strip():
        modifications["Video.source"] = args.video_source.strip()

    print("Submitting Creatomate intro render...")
    render = create_render(TEMPLATE_ID, modifications)
    render_id = render["id"]
    final_render = wait_for_render(render_id)
    output_url = final_render.get("url")
    if not output_url:
        raise RuntimeError(f"Creatomate render succeeded but returned no URL: {final_render}")

    output_path = Path(args.output)
    download_file(output_url, output_path)
    print(f"Creatomate intro saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
