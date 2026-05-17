import argparse
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests
from dotenv import load_dotenv


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TOKEN_FILE = BASE_DIR / "tiktok_token.json"
AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
DEFAULT_SCOPE = "video.upload"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Authorize a TikTok account for draft uploads.")
    parser.add_argument("--token-file", default=str(TOKEN_FILE))
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    return parser.parse_args()


def get_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


class CallbackHandler(BaseHTTPRequestHandler):
    server_version = "TikTokAuth/1.0"

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != self.server.callback_path:
            self.send_error(404, "Not found")
            return

        query = urllib.parse.parse_qs(parsed.query)
        self.server.auth_code = query.get("code", [None])[0]
        self.server.auth_state = query.get("state", [None])[0]
        self.server.auth_error = query.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>TikTok authorization received.</h1>"
            b"<p>You can close this window and return to the terminal.</p></body></html>"
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def build_auth_url(client_key: str, redirect_uri: str, scope: str, state: str) -> str:
    params = {
        "client_key": client_key,
        "response_type": "code",
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def wait_for_callback(redirect_uri: str, timeout_seconds: int = 300) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 80
    callback_path = parsed.path or "/"

    httpd = HTTPServer((host, port), CallbackHandler)
    httpd.callback_path = callback_path
    httpd.auth_code = None
    httpd.auth_state = None
    httpd.auth_error = None

    thread = threading.Thread(target=httpd.handle_request, daemon=True)
    thread.start()

    started = time.time()
    while time.time() - started < timeout_seconds:
        if httpd.auth_error:
            raise RuntimeError(f"TikTok auth failed: {httpd.auth_error}")
        if httpd.auth_code:
            return httpd.auth_code, httpd.auth_state
        time.sleep(0.2)

    raise TimeoutError("Timed out waiting for TikTok authorization callback.")


def exchange_code_for_token(client_key: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def main() -> int:
    args = parse_args()
    client_key = get_env("TIKTOK_CLIENT_KEY")
    client_secret = get_env("TIKTOK_CLIENT_SECRET")
    redirect_uri = get_env("TIKTOK_REDIRECT_URI")

    state = secrets.token_urlsafe(24)
    auth_url = build_auth_url(client_key, redirect_uri, args.scope, state)

    print("Open this URL to authorize TikTok:")
    print(auth_url)
    webbrowser.open(auth_url)

    code, returned_state = wait_for_callback(redirect_uri)
    if returned_state != state:
        raise RuntimeError("State mismatch in TikTok OAuth callback.")

    token_bundle = exchange_code_for_token(client_key, client_secret, code, redirect_uri)
    Path(args.token_file).write_text(json.dumps(token_bundle, indent=2), encoding="utf-8")
    print(f"TikTok token saved to: {Path(args.token_file)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
