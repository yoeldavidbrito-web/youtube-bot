import argparse
import os
import time
from pathlib import Path
from urllib.request import urlretrieve

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "luma_clip.mp4"
DEFAULT_RATIO = "9:16"
DEFAULT_DURATION = 5
DEFAULT_MODEL = "ray-2"
API_BASE = "https://api.lumalabs.ai/dream-machine/v1"
POLL_INTERVAL = 8
MAX_WAIT = 600

TOPIC_PROMPTS = {
    "dahmer": [
        (
            "Dark Milwaukee apartment building hallway at night, 1978, flickering fluorescent tube light, "
            "worn carpet, numbered unit doors, oppressive stillness, crime scene atmosphere, "
            "16mm film grain, slow camera drift, no people, cinematic horror documentary"
        ),
        (
            "Milwaukee police detective examining black and white crime scene photographs spread across a desk, "
            "1991, harsh overhead lamp, stacks of case files, handwritten notes, cold institutional atmosphere, "
            "cinematic documentary realism, no gore"
        ),
        (
            "Courtroom interior 1992, dark wood paneling, fluorescent overhead lights, "
            "empty defendant chair, thick stack of legal binders, gavel on bench, "
            "tense legal atmosphere, desaturated color, documentary cinematography"
        ),
        (
            "Milwaukee apartment exterior at night, 1991, police cruisers with lights flashing blue and red, "
            "crime scene tape across building entrance, news cameras, crowd of onlookers, "
            "tense investigative documentary, cinematic wide shot"
        ),
    ],
    "zodiac": [
        (
            "Northern California highway at night, 1969, lonely stretch of road, distant headlights, "
            "fog rolling in, police flashlight searching darkness, investigative tension, "
            "cinematic 16mm grain, slow camera pan"
        ),
        (
            "Newspaper front page close-up, 1969, headline about unsolved cipher murders, "
            "stamped envelope with strange symbols, ink-stained fingers turning the page, "
            "dramatic side lighting, documentary realism"
        ),
    ],
    "bundy": [
        (
            "Quiet suburban street at night, 1974, parked Volkswagen Beetle under a streetlamp, "
            "shadows between houses, ominous stillness, slow camera push, "
            "cinematic horror documentary, no people"
        ),
        (
            "Florida state courthouse exterior, 1979, summer heat haze, press gathered outside, "
            "microphones and cameras, tense atmosphere, cinematic wide shot, documentary realism"
        ),
    ],
    "ramirez": [
        (
            "Los Angeles street at night, 1985, open window on second floor, curtain moving slightly in the breeze, "
            "distant streetlights, ominous stillness, cinematic horror atmosphere, no people, slow zoom"
        ),
    ],
    "btk": [
        (
            "Wichita Kansas suburban neighborhood, 1974, winter snow on the ground, "
            "ordinary houses with lights on inside, mail in the mailbox, ominous quiet, "
            "16mm film grain, slow dolly shot, documentary realism"
        ),
    ],
}

GENERIC_PROMPTS = [
    (
        "Cinematic true crime documentary atmosphere, dark interior, single lamp casting hard shadows, "
        "crime scene evidence on a table, investigators in background, "
        "desaturated color grading, 16mm film grain, slow camera movement"
    ),
    (
        "Empty city street at night, rain reflecting streetlights, police cruiser parked in distance, "
        "crime scene tape, forensic tent, tense investigative atmosphere, "
        "cinematic wide angle, no people in foreground"
    ),
    (
        "Cold case evidence wall in a detective's office, photographs pinned to cork board, "
        "red string connecting clues, newspaper clippings, dim desk lamp, "
        "documentary cinematography, slow zoom in"
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a cinematic video clip with Luma AI.")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--ratio", default=DEFAULT_RATIO)
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=["ray-2", "ray-flash-2"])
    parser.add_argument("--prompt-text", default="", help="Override the generated prompt.")
    parser.add_argument("--scene-index", type=int, default=0, help="Which scene prompt to use (0-based).")
    return parser.parse_args()


def load_api_key() -> str:
    key = os.getenv("LUMAAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "LUMAAI_API_KEY not found. Get your key at https://lumalabs.ai/dream-machine/api/keys "
            "and add it to your .env file: LUMAAI_API_KEY=luma-..."
        )
    return key


def pick_prompt(topic: str, scene_index: int) -> str:
    lower = topic.lower()
    for key, prompts in TOPIC_PROMPTS.items():
        if key in lower:
            return prompts[scene_index % len(prompts)]
    return GENERIC_PROMPTS[scene_index % len(GENERIC_PROMPTS)]


def create_generation(api_key: str, prompt: str, ratio: str, model: str) -> str:
    resp = requests.post(
        f"{API_BASE}/generations",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"prompt": prompt, "aspect_ratio": ratio, "loop": False, "model": model},
        timeout=30,
    )
    resp.raise_for_status()
    generation_id = resp.json()["id"]
    print(f"Luma generation started: {generation_id}")
    return generation_id


def wait_for_generation(api_key: str, generation_id: str) -> str:
    print("Waiting for Luma AI", end="", flush=True)
    elapsed = 0
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        resp = requests.get(
            f"{API_BASE}/generations/{generation_id}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        state = data.get("state", "")
        print(".", end="", flush=True)
        if state == "completed":
            video_url = data.get("assets", {}).get("video", "")
            if not video_url:
                raise RuntimeError("Luma returned no video URL.")
            print(f"\nCompleted: {video_url}")
            return video_url
        if state == "failed":
            raise RuntimeError(f"Luma generation failed: {data.get('failure_reason', data)}")
    raise TimeoutError(f"Luma did not finish in {MAX_WAIT}s.")


def main() -> int:
    args = parse_args()
    api_key = load_api_key()
    prompt = args.prompt_text.strip() or pick_prompt(args.topic, args.scene_index)
    print(f"Prompt: {prompt[:120]}...")

    generation_id = create_generation(api_key, prompt, args.ratio, args.model)
    video_url = wait_for_generation(api_key, generation_id)

    output = Path(args.output)
    urlretrieve(video_url, output)
    print(f"Luma clip saved to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
