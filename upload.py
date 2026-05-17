import argparse
import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload


BASE_DIR = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = BASE_DIR / "client_secret.json"
TOKEN_FILE = BASE_DIR / "youtube_token.json"
REDIRECT_HOST = "localhost"
REDIRECT_PORT = 8765
DEFAULT_VIDEO = BASE_DIR / "video.mp4"
DEFAULT_THUMBNAIL = BASE_DIR / "thumbnail.png"
DEFAULT_METADATA = BASE_DIR / "metadata.json"
DEFAULT_TITLE = "Crime Files | True Crime Documentary"
DEFAULT_DESCRIPTION = (
    "Welcome to Crime Files.\n\n"
    "We cover disturbing real cases, unsolved mysteries, and true crime stories with a darker documentary style. "
    "Subscribe and turn on notifications for more weekly uploads.\n\n"
    "#CrimeFiles #TrueCrime #UnsolvedMystery #CrimeDocumentary #SerialKiller"
)
DEFAULT_TAGS = [
    "true crime", "crime files", "unsolved mystery", "crime documentary", "serial killer",
    "real crime stories", "criminal investigation", "dark documentary", "mystery", "unsolved case"
]
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sube un video a YouTube.")
    parser.add_argument("--client-secret", default=str(CLIENT_SECRET_FILE))
    parser.add_argument("--token", default=str(TOKEN_FILE))
    parser.add_argument("--video", default=str(DEFAULT_VIDEO))
    parser.add_argument("--thumbnail", default=str(DEFAULT_THUMBNAIL))
    parser.add_argument("--metadata", default=str(DEFAULT_METADATA))
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION)
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    return parser.parse_args()


def load_metadata(metadata_path: Path) -> dict:
    if not metadata_path.is_file():
        return {}
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_credentials(client_secret_path: Path, token_path: Path) -> Credentials:
    creds = None

    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except RefreshError:
            try:
                token_path.unlink()
            except FileNotFoundError:
                pass
            creds = None

    if not client_secret_path.is_file():
        raise FileNotFoundError(
            f"No existe el archivo OAuth: {client_secret_path}. "
            "Descarga un OAuth client de tipo Desktop App y guardalo como client_secret.json."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
    creds = flow.run_local_server(
        host=REDIRECT_HOST,
        port=REDIRECT_PORT,
        authorization_prompt_message="Se abrira tu navegador para autorizar YouTube...",
        success_message="Autorizacion completada. Ya puedes volver a la consola.",
        open_browser=True,
    )
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def upload_video(
    youtube,
    video_path: Path,
    thumbnail_path: Path | None,
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
) -> str:
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "25",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 5,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"Subiendo: {video_path.name}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Progreso: {pct}%", end="\r")

    video_id = response["id"]
    print(f"\nVideo subido correctamente.")
    print(f"URL: https://www.youtube.com/watch?v={video_id}")
    print(f"Privacy: {privacy}")

    if thumbnail_path and thumbnail_path.is_file():
        try:
            thumb_media = MediaFileUpload(str(thumbnail_path), resumable=False)
            youtube.thumbnails().set(videoId=video_id, media_body=thumb_media).execute()
            print(f"Thumbnail aplicada: {thumbnail_path.name}")
        except HttpError as exc:
            print(f"Warning: no se pudo aplicar la thumbnail ({exc.status_code}). El video sigue subido.")

    return video_id


if __name__ == "__main__":
    args = parse_args()
    creds = load_credentials(Path(args.client_secret), Path(args.token))
    youtube = build("youtube", "v3", credentials=creds)
    metadata = load_metadata(Path(args.metadata))

    video_path = Path(args.video)
    if not video_path.is_file():
        raise FileNotFoundError(f"No existe el video: {video_path}")

    title = metadata.get("title", DEFAULT_TITLE)
    if args.title != DEFAULT_TITLE:
        title = args.title

    description = metadata.get("description", DEFAULT_DESCRIPTION)
    if args.description != DEFAULT_DESCRIPTION:
        description = args.description

    tags = metadata.get("tags", DEFAULT_TAGS)

    upload_video(
        youtube=youtube,
        video_path=video_path,
        thumbnail_path=Path(args.thumbnail) if Path(args.thumbnail).is_file() else None,
        title=title,
        description=description,
        tags=tags,
        privacy=args.privacy,
    )
