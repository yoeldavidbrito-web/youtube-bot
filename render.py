"""
render.py — genera video.mp4 usando JSON2Video (render en la nube).
Reemplaza video.py: no necesita MoviePy ni CPU local para renderizar.

Flujo:
  1. Sube audio.mp3 a JSON2Video
  2. Sube music.wav a JSON2Video (si existe)
  3. Construye el proyecto JSON con titulo, subtitulos sincronizados y musica
  4. Envia el proyecto a JSON2Video
  5. Espera que termine el render
  6. Descarga video.mp4
"""

import json
import os
import time
import argparse
import requests
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
API_KEY = os.getenv("JSON2VIDEO_API_KEY", "")
API_BASE = "https://api.json2video.com/v2"

DEFAULT_AUDIO = BASE_DIR / "audio.mp3"
DEFAULT_MUSIC = BASE_DIR / "music.wav"
DEFAULT_TIMESTAMPS = BASE_DIR / "timestamps.json"
DEFAULT_OUTPUT = BASE_DIR / "video.mp4"
DEFAULT_TOPIC = "Caso Criminal"

WORDS_PER_SUBTITLE = 8
TITLE_DURATION = 4        # segundos pantalla de titulo
POLL_INTERVAL = 10        # segundos entre checks de estado
MAX_WAIT = 600            # timeout maximo en segundos


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Renderiza video en la nube con JSON2Video.")
    parser.add_argument("--audio", default=str(DEFAULT_AUDIO))
    parser.add_argument("--music", default=str(DEFAULT_MUSIC))
    parser.add_argument("--timestamps", default=str(DEFAULT_TIMESTAMPS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    return parser.parse_args()


def headers() -> dict:
    return {"x-api-key": API_KEY}


# ──────────────────────────────────────────────
# 1. Subir archivos a JSON2Video
# ──────────────────────────────────────────────

def upload_file(file_path: Path) -> str:
    """Sube archivo a filebin.net y retorna URL directa de descarga."""
    import uuid
    bin_name = f"csf-{uuid.uuid4().hex[:10]}"
    filename = file_path.name
    print(f"  Subiendo {filename} a filebin.net...")
    with open(file_path, "rb") as f:
        r = requests.post(
            f"https://filebin.net/{bin_name}/{filename}",
            headers={
                "Content-Type": "application/octet-stream",
                "filename": filename,
            },
            data=f,
            timeout=120,
        )
    r.raise_for_status()
    url = f"https://filebin.net/{bin_name}/{filename}"
    print(f"  OK: {url}")
    return url


# ──────────────────────────────────────────────
# 2. Construir subtitulos desde timestamps
# ──────────────────────────────────────────────

def load_subtitles(timestamps_path: Path) -> list[dict]:
    if not timestamps_path.is_file():
        return []
    word_boundaries = json.loads(timestamps_path.read_text(encoding="utf-8"))
    subtitles = []
    for i in range(0, len(word_boundaries), WORDS_PER_SUBTITLE):
        chunk = word_boundaries[i: i + WORDS_PER_SUBTITLE]
        text = " ".join(w["word"] for w in chunk)
        start = round(TITLE_DURATION + chunk[0]["start"], 3)
        end = round(TITLE_DURATION + chunk[-1]["start"] + chunk[-1]["duration"], 3)
        subtitles.append({"text": text, "start": start, "end": end})
    return subtitles


# ──────────────────────────────────────────────
# 3. Construir proyecto JSON2Video
# ──────────────────────────────────────────────

def text_el(text, font_size, color, x, y, z=5, duration=None, start=None, width=None, bg=None, bg_pad=None, wrap=False):
    el = {
        "type": "text",
        "text": text,
        "font-family": "Impact",
        "font-size": font_size,
        "font-color": color,
        "x": x,
        "y": y,
        "origin": ["50%", "50%"],
        "z-index": z,
    }
    if duration is not None:
        el["duration"] = duration
    if start is not None:
        el["start-time"] = start
    if width is not None:
        el["width"] = width
        el["word-wrap"] = wrap
    if bg is not None:
        el["background-color"] = bg
        el["background-padding"] = bg_pad or 16
    return el


def build_project(
    topic: str,
    audio_url: str,
    music_url: str | None,
    subtitles: list[dict],
    audio_duration: float,
) -> dict:

    watermark = {
        "type": "text",
        "text": "CSF",
        "font-family": "Impact",
        "font-size": 38,
        "font-color": "rgba(255,255,255,0.55)",
        "x": 1820,
        "y": 1040,
        "z-index": 20,
    }

    # ── Escena 1: Titulo ──────────────────────────────────────
    title_elements = [
        text_el("CASO REAL", 36, "#CC2200", "50%", "38%", z=5, duration=TITLE_DURATION),
        text_el(topic.upper(), 68, "#FFFFFF", "50%", "50%", z=5, duration=TITLE_DURATION, width=1536, wrap=True),
        watermark,
    ]
    if music_url:
        title_elements.append({
            "type": "audio",
            "src": music_url,
            "volume": 0.12,
            "z-index": 1,
        })

    scene_title = {
        "comment": "Titulo",
        "background-color": "#0A0A0A",
        "duration": TITLE_DURATION,
        "elements": title_elements,
    }

    # ── Escena 2: Contenido principal ─────────────────────────
    content_elements = [
        {
            "type": "audio",
            "src": audio_url,
            "volume": 1.0,
            "z-index": 2,
        },
        watermark,
    ]
    if music_url:
        content_elements.append({
            "type": "audio",
            "src": music_url,
            "volume": 0.12,
            "loop": -1,
            "z-index": 1,
        })

    # Subtitulos con start-time relativo a esta escena
    for sub in subtitles:
        dur = round(sub["end"] - sub["start"], 3)
        content_elements.append(
            text_el(
                sub["text"], 52, "#FFFFFF",
                "50%", "88%",
                z=10,
                start=round(sub["start"], 3),
                duration=dur,
                width=1632,
                wrap=True,
                bg="rgba(0,0,0,0.75)",
                bg_pad=16,
            )
        )

    scene_content = {
        "comment": "Contenido",
        "background-color": "#0A0A0A",
        "duration": round(audio_duration, 2),
        "elements": content_elements,
    }

    return {
        "resolution": "full-hd",
        "quality": "high",
        "scenes": [scene_title, scene_content],
    }


# ──────────────────────────────────────────────
# 4. Enviar proyecto y esperar render
# ──────────────────────────────────────────────

def submit_project(project: dict) -> str:
    print("Enviando proyecto a JSON2Video...")
    r = requests.post(
        f"{API_BASE}/movies",
        headers={**headers(), "Content-Type": "application/json"},
        json=project,
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    project_id = data.get("project") or data.get("data", {}).get("project")
    if not project_id:
        raise RuntimeError(f"No se obtuvo project ID: {data}")
    print(f"Proyecto enviado. ID: {project_id}")
    return project_id


def wait_for_render(project_id: str) -> str:
    print("Esperando render en la nube", end="", flush=True)
    elapsed = 0
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        r = requests.get(
            f"{API_BASE}/movies",
            headers=headers(),
            params={"project": project_id},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        movie = data.get("movie") or (data.get("data") or [{}])[0]
        status = movie.get("status", "")
        print(".", end="", flush=True)
        if status == "done":
            url = movie.get("url")
            print(f"\nRender completado.")
            return url
        if status == "error":
            raise RuntimeError(f"JSON2Video reporto error: {movie}")
    raise TimeoutError(f"El render no termino en {MAX_WAIT}s.")


def download_video(url: str, output_path: Path) -> None:
    print(f"Descargando video...")
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
    print(f"Video guardado en: {output_path}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def render(
    topic: str,
    audio_path: Path,
    music_path: Path | None,
    timestamps_path: Path,
    output_path: Path,
) -> None:
    if not API_KEY:
        raise RuntimeError("Falta JSON2VIDEO_API_KEY en .env")
    if not audio_path.is_file():
        raise FileNotFoundError(f"No existe el audio: {audio_path}")

    print("\n[1/6] Subiendo archivos...")
    audio_url = upload_file(audio_path)

    music_url = None
    if music_path and music_path.is_file():
        # Convierte WAV a MP3 si es necesario
        if music_path.suffix.lower() == ".wav":
            music_mp3 = music_path.with_suffix(".upload.mp3")
            if not music_mp3.is_file():
                from moviepy.editor import AudioFileClip as _AC
                _AC(str(music_path)).write_audiofile(str(music_mp3), logger=None)
            music_url = upload_file(music_mp3)
        else:
            music_url = upload_file(music_path)

    print("\n[2/6] Cargando subtitulos...")
    subtitles = load_subtitles(timestamps_path)
    print(f"  {len(subtitles)} subtitulos sincronizados")

    print("\n[3/6] Calculando duracion...")
    from moviepy.editor import AudioFileClip
    clip = AudioFileClip(str(audio_path))
    audio_duration = clip.duration
    total_duration = round(audio_duration + TITLE_DURATION, 2)
    clip.close()
    print(f"  Duracion total: {total_duration}s")

    print("\n[4/6] Construyendo proyecto JSON...")
    project = build_project(topic, audio_url, music_url, subtitles, audio_duration)

    print("\n[5/6] Enviando a JSON2Video...")
    project_id = submit_project(project)

    print("\n[6/6] Esperando render en la nube...")
    video_url = wait_for_render(project_id)

    download_video(video_url, output_path)
    print(f"\nListo: {output_path}")


if __name__ == "__main__":
    args = parse_args()
    render(
        topic=args.topic,
        audio_path=Path(args.audio),
        music_path=Path(args.music) if Path(args.music).is_file() else None,
        timestamps_path=Path(args.timestamps),
        output_path=Path(args.output),
    )
