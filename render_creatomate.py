"""
render_creatomate.py — genera video.mp4 usando Creatomate (render en la nube).
Flujo:
  1. Sube audio y música a Creatomate Assets
  2. Construye composición con titulo, subtítulos sincronizados y música
  3. Envía el render y espera
  4. Descarga video.mp4
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
API_KEY = os.getenv("CREATOMATE_API_KEY", "")
API_BASE = "https://api.creatomate.com/v1"

DEFAULT_AUDIO = BASE_DIR / "audio.mp3"
DEFAULT_MUSIC = BASE_DIR / "music.upload.mp3"
DEFAULT_TIMESTAMPS = BASE_DIR / "timestamps.json"
DEFAULT_OUTPUT = BASE_DIR / "video.mp4"
DEFAULT_TOPIC = "Caso Criminal"

WORDS_PER_SUBTITLE = 8
TITLE_DURATION = 4.0
POLL_INTERVAL = 8
MAX_WAIT = 600


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Renderiza video en la nube con Creatomate.")
    parser.add_argument("--audio", default=str(DEFAULT_AUDIO))
    parser.add_argument("--music", default=str(DEFAULT_MUSIC))
    parser.add_argument("--timestamps", default=str(DEFAULT_TIMESTAMPS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    return parser.parse_args()


def auth() -> dict:
    return {"Authorization": f"Bearer {API_KEY}"}


# ─── 1. Subir archivos a Creatomate Assets ───────────────────

def upload_asset(file_path: Path) -> str:
    """Sube archivo a uguu.se y retorna URL directa de descarga."""
    filename = file_path.name
    print(f"  Subiendo {filename}...")
    with open(file_path, "rb") as f:
        r = requests.post(
            "https://uguu.se/upload",
            files={"files[]": (filename, f)},
            timeout=120,
        )
    r.raise_for_status()
    data = r.json()
    url = data["files"][0]["url"]
    print(f"  OK: {url}")
    return url


# ─── 2. Subtítulos desde timestamps ──────────────────────────

def load_subtitles(timestamps_path: Path) -> list[dict]:
    if not timestamps_path.is_file():
        return []
    words = json.loads(timestamps_path.read_text(encoding="utf-8"))
    subtitles = []
    for i in range(0, len(words), WORDS_PER_SUBTITLE):
        chunk = words[i: i + WORDS_PER_SUBTITLE]
        text = " ".join(w["word"] for w in chunk)
        start = round(TITLE_DURATION + chunk[0]["start"], 3)
        end = round(TITLE_DURATION + chunk[-1]["start"] + chunk[-1]["duration"], 3)
        subtitles.append({"text": text, "start": start, "end": end})
    return subtitles


# ─── 3. Construir composición ────────────────────────────────

def build_source(
    topic: str,
    audio_url: str,
    music_url: str | None,
    subtitles: list[dict],
    audio_duration: float,
) -> dict:
    total = round(TITLE_DURATION + audio_duration, 2)
    elements = []

    # Música de fondo
    if music_url:
        elements.append({
            "type": "audio",
            "source": music_url,
            "volume": "12%",
            "duration": total,
        })

    # Audio principal (voz)
    elements.append({
        "type": "audio",
        "source": audio_url,
        "time": TITLE_DURATION,
        "volume": "100%",
    })

    # Pantalla de título
    elements.append({
        "type": "text",
        "text": "CASO REAL",
        "font_family": "Oswald",
        "font_weight": "700",
        "font_size": 36,
        "fill_color": "#CC2200",
        "x": "50%",
        "y": "38%",
        "x_anchor": "50%",
        "y_anchor": "50%",
        "duration": TITLE_DURATION,
    })
    elements.append({
        "type": "text",
        "text": topic.upper(),
        "font_family": "Oswald",
        "font_weight": "700",
        "font_size": 64,
        "fill_color": "#FFFFFF",
        "x": "50%",
        "y": "52%",
        "width": "80%",
        "x_anchor": "50%",
        "y_anchor": "50%",
        "x_alignment": "50%",
        "duration": TITLE_DURATION,
    })

    # Subtítulos sincronizados
    for sub in subtitles:
        dur = round(sub["end"] - sub["start"], 3)
        elements.append({
            "type": "text",
            "text": sub["text"],
            "font_family": "Oswald",
            "font_weight": "600",
            "font_size": 48,
            "fill_color": "#FFFFFF",
            "background_color": "rgba(0,0,0,0.78)",
            "background_x_padding": "8%",
            "background_y_padding": "4%",
            "x": "50%",
            "y": "88%",
            "width": "85%",
            "x_anchor": "50%",
            "y_anchor": "50%",
            "x_alignment": "50%",
            "time": sub["start"],
            "duration": dur,
        })

    # Watermark CSF
    elements.append({
        "type": "text",
        "text": "CSF",
        "font_family": "Oswald",
        "font_weight": "700",
        "font_size": 32,
        "fill_color": "rgba(255,255,255,0.45)",
        "x": "95%",
        "y": "95%",
        "x_anchor": "100%",
        "y_anchor": "100%",
        "duration": total,
    })

    return {
        "output_format": "mp4",
        "width": 1920,
        "height": 1080,
        "fill_color": "#0A0A0A",
        "duration": total,
        "frame_rate": 24,
        "elements": elements,
    }


# ─── 4. Enviar render y esperar ───────────────────────────────

def submit_render(source: dict) -> str:
    print("Enviando proyecto a Creatomate...")
    r = requests.post(
        f"{API_BASE}/renders",
        headers={**auth(), "Content-Type": "application/json"},
        json={"source": source},
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    renders = data if isinstance(data, list) else [data]
    render_id = renders[0]["id"]
    print(f"Render iniciado. ID: {render_id}")
    return render_id


def wait_for_render(render_id: str) -> str:
    print("Renderizando en la nube", end="", flush=True)
    elapsed = 0
    while elapsed < MAX_WAIT:
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
        r = requests.get(f"{API_BASE}/renders/{render_id}", headers=auth(), timeout=30)
        data = r.json()
        status = data.get("status", "")
        print(".", end="", flush=True)
        if status == "succeeded":
            print(f"\nRender completado en {elapsed}s.")
            return data["url"]
        if status == "failed":
            raise RuntimeError(f"Creatomate error: {data.get('error_message', 'desconocido')}")
    raise TimeoutError(f"El render no termino en {MAX_WAIT}s.")


def download_video(url: str, output_path: Path) -> None:
    print(f"Descargando video...")
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in r.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
    size_mb = output_path.stat().st_size / 1024 / 1024
    print(f"Video guardado en: {output_path} ({size_mb:.1f} MB)")


# ─── Main ─────────────────────────────────────────────────────

def render(
    topic: str,
    audio_path: Path,
    music_path: Path | None,
    timestamps_path: Path,
    output_path: Path,
) -> None:
    if not API_KEY:
        raise RuntimeError("Falta CREATOMATE_API_KEY en .env")
    if not audio_path.is_file():
        raise FileNotFoundError(f"No existe el audio: {audio_path}")

    print("\n[1/5] Subiendo archivos...")
    audio_url = upload_asset(audio_path)
    music_url = upload_asset(music_path) if music_path and music_path.is_file() else None

    print("\n[2/5] Calculando duracion...")
    from moviepy.editor import AudioFileClip
    clip = AudioFileClip(str(audio_path))
    audio_duration = clip.duration
    clip.close()
    print(f"  Audio: {audio_duration:.1f}s | Total: {TITLE_DURATION + audio_duration:.1f}s")

    print("\n[3/5] Cargando subtitulos...")
    subtitles = load_subtitles(timestamps_path)
    print(f"  {len(subtitles)} subtitulos sincronizados")

    print("\n[4/5] Enviando a Creatomate...")
    source = build_source(topic, audio_url, music_url, subtitles, audio_duration)
    render_id = submit_render(source)

    print("\n[5/5] Esperando render...")
    video_url = wait_for_render(render_id)
    download_video(video_url, output_path)
    print(f"\nListo: {output_path}")


if __name__ == "__main__":
    args = parse_args()
    music_path = Path(args.music)
    render(
        topic=args.topic,
        audio_path=Path(args.audio),
        music_path=music_path if music_path.is_file() else None,
        timestamps_path=Path(args.timestamps),
        output_path=Path(args.output),
    )
