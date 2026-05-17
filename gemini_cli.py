import os
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
GEMINI_CMD = Path(r"C:\Users\yoeld\AppData\Roaming\npm\gemini.cmd")

FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-3-flash-preview")
PREMIUM_MODEL = os.getenv("GEMINI_PREMIUM_MODEL", "gemini-3-pro-preview")
STABLE_FALLBACK_MODEL = os.getenv("GEMINI_STABLE_FALLBACK_MODEL", "gemini-2.5-flash")
IMAGE_MODEL = os.getenv("GEMINI_IMAGE_MODEL", "gemini-3-pro-image-preview")


def model_chain(premium: bool = False) -> list[str]:
    if premium:
        return [PREMIUM_MODEL, FAST_MODEL, STABLE_FALLBACK_MODEL]
    return [FAST_MODEL, STABLE_FALLBACK_MODEL]


def run_gemini_cli(prompt: str, *, premium: bool = False, timeout_seconds: tuple[int, ...] = (120, 240)) -> str:
    safe_prompt = prompt.replace('"', '\\"')
    last_error = None
    for model in model_chain(premium):
        for timeout in timeout_seconds:
            try:
                result = subprocess.run(
                    f'"{GEMINI_CMD}" --model "{model}" -p "{safe_prompt}"',
                    cwd=BASE_DIR,
                    shell=True,
                    capture_output=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                last_error = f"{model} timed out after {timeout}s"
                continue

            output = result.stdout.decode("utf-8", errors="replace").strip()
            if result.returncode == 0 and output:
                return output
            error = result.stderr.decode("utf-8", errors="replace").strip()
            last_error = error or f"{model} returned no output"

    raise RuntimeError(f"Gemini CLI error: {last_error}")
