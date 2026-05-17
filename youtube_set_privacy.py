import argparse
from pathlib import Path

from googleapiclient.discovery import build

from upload import CLIENT_SECRET_FILE, TOKEN_FILE, load_credentials


BASE_DIR = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update privacy for one or more YouTube videos.")
    parser.add_argument("--client-secret", default=str(CLIENT_SECRET_FILE))
    parser.add_argument("--token", default=str(TOKEN_FILE))
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    parser.add_argument("--video-ids", nargs="+", required=True)
    return parser.parse_args()


def update_privacy(youtube, video_id: str, privacy: str) -> None:
    response = youtube.videos().list(part="snippet,status", id=video_id).execute()
    items = response.get("items", [])
    if not items:
        print(f"{video_id}: not found or not accessible")
        return

    item = items[0]
    body = {
        "id": video_id,
        "snippet": {
            "categoryId": item["snippet"].get("categoryId", "25"),
            "title": item["snippet"]["title"],
            "description": item["snippet"].get("description", ""),
            "tags": item["snippet"].get("tags", []),
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": item["status"].get("selfDeclaredMadeForKids", False),
        },
    }
    youtube.videos().update(part="snippet,status", body=body).execute()
    print(f"{video_id}: set to {privacy}")


def main() -> int:
    args = parse_args()
    creds = load_credentials(Path(args.client_secret), Path(args.token))
    youtube = build("youtube", "v3", credentials=creds)
    for video_id in args.video_ids:
        update_privacy(youtube, video_id, args.privacy)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
