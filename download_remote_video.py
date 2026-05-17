import argparse
from pathlib import Path

import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download a remote MP4 render to a local file.")
    parser.add_argument("--url-file", required=True, help="Path to a text file containing the remote video URL.")
    parser.add_argument("--output", required=True, help="Local MP4 output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    url_file = Path(args.url_file)
    output = Path(args.output)

    if not url_file.is_file():
        raise FileNotFoundError(f"URL file not found: {url_file}")

    url = url_file.read_text(encoding="utf-8").strip()
    if not url:
        raise ValueError("The URL file is empty.")

    response = requests.get(url, timeout=600)
    response.raise_for_status()
    output.write_bytes(response.content)
    print(f"Downloaded video to: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
