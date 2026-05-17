import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from topic_finder import find_topic


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VIDEOS_PER_DAY = 3
UPLOADED_FILE = BASE_DIR / "uploaded_topics.json"

TEMAS = [
    ("The Zodiac Killer", "The Zodiac Killer | The Unsolved Case That Still Terrifies America"),
    ("Ted Bundy", "Ted Bundy | The Charming Monster Nobody Stopped In Time"),
    ("Jack the Ripper", "Jack the Ripper | The Killer London Never Caught"),
    ("Jeffrey Dahmer", "Jeffrey Dahmer | The Disturbing Story Behind The Murders"),
    ("BTK Killer", "BTK Killer | The Serial Murderer Who Mocked The Police"),
    ("Aileen Wuornos", "Aileen Wuornos | America's Most Notorious Female Serial Killer"),
    ("John Wayne Gacy", "John Wayne Gacy | The Killer Clown Next Door"),
    ("Charles Manson", "Charles Manson | The Cult Leader Behind The Horror"),
    ("Ed Gein", "Ed Gein | The Butcher Of Plainfield"),
    ("Richard Ramirez", "Richard Ramirez | Inside The Night Stalker's Terror"),
    ("Lizzie Borden", "Lizzie Borden | The Family Murder That Shocked America"),
    ("Son of Sam", "Son of Sam | The Serial Killer Who Sent The Letters"),
    ("Andrei Chikatilo", "Andrei Chikatilo | The Rostov Ripper Files"),
    ("The Black Dahlia", "The Black Dahlia | Hollywood's Most Chilling Unsolved Murder"),
    ("The Cleveland Torso Murderer", "The Cleveland Torso Murderer | America's Forgotten Nightmare"),
]

INDICE_FILE = BASE_DIR / "tema_indice.txt"


def load_uploaded() -> set[str]:
    if not UPLOADED_FILE.is_file():
        return set()
    try:
        data = json.loads(UPLOADED_FILE.read_text(encoding="utf-8"))
        return {t.lower().strip() for t in data.get("uploaded", [])}
    except Exception:
        return set()


def mark_uploaded(tema: str) -> None:
    try:
        if UPLOADED_FILE.is_file():
            data = json.loads(UPLOADED_FILE.read_text(encoding="utf-8"))
        else:
            data = {"uploaded": []}
        uploaded = data.get("uploaded", [])
        if tema not in uploaded:
            uploaded.append(tema)
        data["uploaded"] = uploaded
        UPLOADED_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[Warning] No se pudo guardar el tema en uploaded_topics.json: {exc}")


def is_uploaded(tema: str) -> bool:
    return tema.lower().strip() in load_uploaded()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ejecuta el pipeline completo de YouTube.")
    parser.add_argument("--loop", action="store_true", help="Mantiene el bot ejecutando videos diarios.")
    parser.add_argument(
        "--videos-per-day",
        type=int,
        default=DEFAULT_VIDEOS_PER_DAY,
        help="Cantidad de videos distintos al dia cuando se usa --loop.",
    )
    parser.add_argument(
        "--batch-count",
        type=int,
        default=1,
        help="Cantidad de videos a ejecutar ahora mismo en esta corrida.",
    )
    parser.add_argument(
        "--renderer",
        default="creatomate",
        choices=["json2video", "creatomate"],
        help="Motor de render final.",
    )
    return parser.parse_args()


def get_next_tema() -> tuple[str, str] | None:
    # Try web search first
    try:
        tema = find_topic()
        if tema:
            return tema, tema
    except Exception as exc:
        print(f"[topic_finder] Web search failed, using hardcoded list: {exc}")

    # Fallback: hardcoded list
    if INDICE_FILE.is_file():
        indice = int(INDICE_FILE.read_text(encoding="utf-8").strip())
    else:
        indice = 0

    for offset in range(len(TEMAS)):
        current = (indice + offset) % len(TEMAS)
        tema, titulo = TEMAS[current]
        if not is_uploaded(tema):
            INDICE_FILE.write_text(str((current + 1) % len(TEMAS)), encoding="utf-8")
            return tema, titulo

    return None  # All topics uploaded


def run(args: list[str], desc: str) -> None:
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {desc}...")
    result = subprocess.run(args, cwd=BASE_DIR)
    if result.returncode != 0:
        raise RuntimeError(f"ERROR en: {desc}")


def pipeline(tema: str, titulo: str, renderer: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"TEMA: {tema}")
    print(f"TITULO: {titulo}")
    print(f"{'=' * 60}")

    python = sys.executable
    run([python, "main.py", "--tema", tema], "Generando guion")
    run([python, "tts.py"], "Generando voz con timestamps")
    run([python, "images.py", "--topic", tema, "--scene-count", "6"], "Generando imagenes del caso")
    run([python, "music.py"], "Generando musica de fondo")
    run([python, "metadata.py", "--topic", tema], "Generando metadata y thumbnail")
    try:
        run([python, "runway_scenes.py"], "Animando escenas con Runway")
    except RuntimeError as exc:
        print(f"[Runway] Omitido (continuando sin animacion): {exc}")

    if renderer == "json2video":
        run([python, "json2video_render.py", "--topic", tema], "Renderizando en la nube con JSON2Video")
        run([python, "download_remote_video.py", "--url-file", "json2video_output_url.txt", "--output", "video.mp4"], "Descargando render final")
    else:
        run([python, "video.py", "--topic", tema, "--output", "base_video.mp4"], "Renderizando corte base")
        run([python, "creatomate_intro.py", "--topic", tema], "Renderizando intro premium")
        run([python, "assemble_video.py", "--intro", "creatomate_intro.mp4", "--main", "base_video.mp4", "--output", "video.mp4"], "Ensamblando video final")

    run([python, "upload.py", "--privacy", "private"], "Subiendo a YouTube")
    mark_uploaded(tema)
    print(f"\n[OK] Video subido correctamente: {titulo}")


def run_batch(batch_count: int, renderer: str) -> None:
    for _ in range(batch_count):
        result = get_next_tema()
        if result is None:
            print("\n[INFO] Todos los temas ya fueron subidos. Agrega nuevos temas a TEMAS en run.py.")
            break
        tema, titulo = result
        pipeline(tema, titulo, renderer)


def main() -> int:
    args = parse_args()

    if args.loop:
        interval_seconds = int(86400 / max(args.videos_per_day, 1))
        print(f"Modo automatico: {args.videos_per_day} videos por dia.")
        while True:
            try:
                run_batch(1, args.renderer)
            except Exception as exc:
                print(f"Error: {exc}")
            print(f"\nEsperando {interval_seconds // 3600} horas para el siguiente video...")
            time.sleep(interval_seconds)
    else:
        run_batch(max(args.batch_count, 1), args.renderer)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
