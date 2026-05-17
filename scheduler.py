import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, time as dt_time, timedelta
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "scheduler_state.json"
DEFAULT_TIME = "09:00"
DEFAULT_VIDEOS_PER_DAY = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Programa la ejecucion diaria del pipeline de YouTube.")
    parser.add_argument("--time", default=DEFAULT_TIME, help="Hora diaria en formato HH:MM.")
    parser.add_argument(
        "--videos-per-day",
        type=int,
        default=DEFAULT_VIDEOS_PER_DAY,
        help="Cantidad de videos distintos a generar/subir por dia.",
    )
    parser.add_argument("--once", action="store_true", help="Ejecuta el lote una sola vez y termina.")
    parser.add_argument("--dry-run", action="store_true", help="No ejecuta nada; solo imprime el plan.")
    return parser.parse_args()


def parse_time(value: str) -> dt_time:
    try:
        hour, minute = value.split(":", 1)
        return dt_time(hour=int(hour), minute=int(minute))
    except Exception as exc:
        raise ValueError(f"Hora invalida: {value}. Usa formato HH:MM.") from exc


def load_state() -> dict:
    if not STATE_FILE.is_file():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(last_run_at: datetime) -> None:
    payload = {
        "last_run_at": last_run_at.isoformat(),
        "last_run_date": last_run_at.date().isoformat(),
    }
    STATE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def next_run_after(now: datetime, scheduled_time: dt_time) -> datetime:
    candidate = now.replace(
        hour=scheduled_time.hour,
        minute=scheduled_time.minute,
        second=0,
        microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def should_run_today(state: dict, now: datetime, scheduled_time: dt_time) -> bool:
    last_run_date = state.get("last_run_date")
    scheduled_today = now.replace(
        hour=scheduled_time.hour,
        minute=scheduled_time.minute,
        second=0,
        microsecond=0,
    )
    return now >= scheduled_today and last_run_date != now.date().isoformat()


def run_batch(videos_per_day: int, dry_run: bool) -> None:
    command = [sys.executable, "run.py", "--batch-count", str(max(videos_per_day, 1))]
    print(f"[scheduler] Ejecutando: {' '.join(command)}")
    if dry_run:
        return
    result = subprocess.run(command, cwd=BASE_DIR)
    if result.returncode != 0:
        raise RuntimeError("El lote diario fallo.")


def run_once(videos_per_day: int, dry_run: bool) -> None:
    run_batch(videos_per_day, dry_run)
    if not dry_run:
        save_state(datetime.now())


def run_forever(scheduled_time: dt_time, videos_per_day: int, dry_run: bool) -> None:
    print(
        f"[scheduler] Activo. Hora diaria: {scheduled_time.strftime('%H:%M')}. "
        f"Videos por dia: {videos_per_day}."
    )
    while True:
        now = datetime.now()
        state = load_state()
        if should_run_today(state, now, scheduled_time):
            run_batch(videos_per_day, dry_run)
            if not dry_run:
                save_state(datetime.now())

        next_run = next_run_after(datetime.now(), scheduled_time)
        wait_seconds = min(max(int((next_run - datetime.now()).total_seconds()), 30), 300)
        print(f"[scheduler] Siguiente verificacion en {wait_seconds}s. Proxima hora objetivo: {next_run}.")
        time.sleep(wait_seconds)


def main() -> int:
    args = parse_args()
    scheduled_time = parse_time(args.time)

    if args.once:
        run_once(args.videos_per_day, args.dry_run)
        return 0

    run_forever(scheduled_time, args.videos_per_day, args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
