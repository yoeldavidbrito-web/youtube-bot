import argparse
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_VIDEO = BASE_DIR / "video.mp4"
DEFAULT_TOKEN_FILE = BASE_DIR / "tiktok_token.json"
OAUTH_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
UPLOAD_INIT_URL = "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload a draft video to TikTok inbox.")
    parser.add_argument("--video", default=str(DEFAULT_VIDEO))
    parser.add_argument("--token-file", default=str(DEFAULT_TOKEN_FILE))
    parser.add_argument("--poll", action="store_true", help="Poll TikTok for publish status after upload.")
    return parser.parse_args()


def get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def load_token_bundle(token_file: Path) -> dict:
    if not token_file.is_file():
        raise FileNotFoundError(f"TikTok token file not found: {token_file}")
    return json.loads(token_file.read_text(encoding="utf-8"))


def save_token_bundle(token_file: Path, bundle: dict) -> None:
    token_file.write_text(json.dumps(bundle, indent=2), encoding="utf-8")


def refresh_access_token(token_bundle: dict, token_file: Path) -> dict:
    response = requests.post(
        OAUTH_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": get_env("TIKTOK_CLIENT_KEY"),
            "client_secret": get_env("TIKTOK_CLIENT_SECRET"),
            "grant_type": "refresh_token",
            "refresh_token": token_bundle["refresh_token"],
        },
        timeout=60,
    )
    response.raise_for_status()
    refreshed = response.json()
    token_bundle.update(refreshed)
    save_token_bundle(token_file, token_bundle)
    return token_bundle


def bearer_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }


def init_video_upload(access_token: str, video_path: Path) -> dict:
    video_size = video_path.stat().st_size
    response = requests.post(
        UPLOAD_INIT_URL,
        headers=bearer_headers(access_token),
        json={
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": video_size,
                "total_chunk_count": 1,
            }
        },
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("error", {}).get("code") != "ok":
        raise RuntimeError(f"TikTok upload init failed: {payload}")
    return payload["data"]


def put_video(upload_url: str, video_path: Path) -> None:
    video_size = video_path.stat().st_size
    with video_path.open("rb") as f:
        response = requests.put(
            upload_url,
            headers={
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
                "Content-Type": "video/mp4",
            },
            data=f,
            timeout=600,
        )
    response.raise_for_status()


def fetch_status(access_token: str, publish_id: str) -> dict:
    response = requests.post(
        STATUS_URL,
        headers=bearer_headers(access_token),
        json={"publish_id": publish_id},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    args = parse_args()
    video_path = Path(args.video)
    token_file = Path(args.token_file)

    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    token_bundle = load_token_bundle(token_file)
    access_token = token_bundle.get("access_token", "")
    if not access_token:
        token_bundle = refresh_access_token(token_bundle, token_file)
        access_token = token_bundle["access_token"]

    init_data = init_video_upload(access_token, video_path)
    publish_id = init_data["publish_id"]
    upload_url = init_data.get("upload_url")

    if not upload_url:
        raise RuntimeError(f"TikTok did not return an upload URL: {init_data}")

    print(f"TikTok publish_id: {publish_id}")
    print("Uploading local video file to TikTok...")
    put_video(upload_url, video_path)
    print("Upload complete. TikTok should send an inbox notification for review.")

    if args.poll:
        for _ in range(20):
            status = fetch_status(access_token, publish_id)
            print(json.dumps(status, indent=2))
            code = status.get("error", {}).get("code")
            if code and code != "ok":
                break
            time.sleep(6)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
