import argparse
import io
import json
import re
import unicodedata
from pathlib import Path
from urllib.request import Request, urlopen

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gemini_cli import run_gemini_cli


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SCRIPT = BASE_DIR / "guion.txt"
DEFAULT_TITLE = BASE_DIR / "title.txt"
DEFAULT_DESCRIPTION = BASE_DIR / "description.txt"
DEFAULT_HASHTAGS = BASE_DIR / "hashtags.txt"
DEFAULT_METADATA = BASE_DIR / "metadata.json"
DEFAULT_THUMBNAIL = BASE_DIR / "thumbnail.png"
FONT_CANDIDATES = [
    "C:/Windows/Fonts/bahnschrift.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/corbelb.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/trebucbd.ttf",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate YouTube metadata.")
    parser.add_argument("--script", default=str(DEFAULT_SCRIPT))
    parser.add_argument("--topic", default="")
    parser.add_argument("--title-file", default=str(DEFAULT_TITLE))
    parser.add_argument("--description-file", default=str(DEFAULT_DESCRIPTION))
    parser.add_argument("--hashtags-file", default=str(DEFAULT_HASHTAGS))
    parser.add_argument("--metadata-file", default=str(DEFAULT_METADATA))
    parser.add_argument("--thumbnail", default=str(DEFAULT_THUMBNAIL))
    parser.add_argument("--premium", action="store_true", help="Use the premium Gemini model chain for metadata.")
    return parser.parse_args()


def load_font(size: int):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def normalize_text(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()).strip()


def normalize_mojibake(text: str) -> str:
    if not isinstance(text, str):
        return text
    try:
        repaired = text.encode("latin-1").decode("utf-8")
        if repaired.count("�") <= text.count("�"):
            return repaired
    except Exception:
        pass
    return text


def ascii_clean(text: str) -> str:
    normalized = normalize_mojibake(text)
    normalized = unicodedata.normalize("NFKD", normalized)
    return normalized.encode("ascii", "ignore").decode("ascii")


def run_gemini(prompt: str, premium: bool = False) -> str:
    output = run_gemini_cli(prompt, premium=premium, timeout_seconds=(120, 240))
    output = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', output)
    output = re.sub(r'^(Gemini|Model|Assistant)\s*:\s*', '', output, flags=re.MULTILINE)
    output = output.strip()
    if not output:
        raise RuntimeError("Gemini CLI returned no output")
    return output


def extract_json_block(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def default_metadata(topic: str) -> dict:
    title = f"{topic} | The Case That Still Haunts America | Killer TimeLine"
    description = (
        f"Tonight on Killer TimeLine, we break down {topic} with a darker, sharper documentary-style retelling.\n\n"
        "If you are into unsolved cases, chilling disappearances, and true crime stories that still disturb people today, "
        "subscribe and turn on notifications for more.\n\n"
        "#KillerTimeLine #TrueCrime #UnsolvedMystery #CriminalCase #DarkDocumentary"
    )
    hashtags = ["#KillerTimeLine", "#TrueCrime", "#UnsolvedMystery", "#CriminalCase", "#DarkDocumentary"]
    tags = [
        "killer timeline",
        "true crime",
        "real crime stories",
        "unsolved mystery",
        "dark documentary",
        topic.lower(),
    ]
    return {
        "title": title[:100],
        "description": description,
        "hashtags": hashtags,
        "tags": tags,
    }


def normalize_topic_key(text: str) -> str:
    cleaned = ascii_clean(text).lower()
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return " ".join(cleaned.split())


def metadata_matches_topic(metadata: dict, topic: str) -> bool:
    topic_key = normalize_topic_key(topic)
    if not topic_key:
        return True
    haystack = normalize_topic_key(
        f"{metadata.get('title', '')} {metadata.get('description', '')} {' '.join(metadata.get('tags', []))}"
    )
    return topic_key in haystack


def build_metadata(topic: str, script: str, premium: bool = False) -> dict:
    prompt = (
        "Act as a YouTube editor for a premium English-language true crime channel. "
        f"Topic: {topic}. "
        "Based on this script, generate a JSON response with these exact keys: "
        "title, description, hashtags, tags. "
        "Rules: title maximum 95 characters, high-CTR but not cheesy. "
        "Description in natural English with 2 short paragraphs and a subscribe CTA. "
        "Hashtags as a list of 5 hashtags. "
        "Tags as a list of 8 YouTube tags. "
        "Return only valid JSON.\n\n"
        f"SCRIPT:\n{script}"
    )
    try:
        raw = run_gemini(prompt, premium=premium)
        parsed = extract_json_block(raw)
        if parsed and all(key in parsed for key in ("title", "description", "hashtags", "tags")):
            parsed["title"] = ascii_clean(str(parsed["title"]))[:100]
            parsed["description"] = ascii_clean(str(parsed["description"]))
            parsed["hashtags"] = [ascii_clean(str(item)) for item in parsed["hashtags"]][:5]
            parsed["tags"] = [ascii_clean(str(item)) for item in parsed["tags"]][:8]
            if metadata_matches_topic(parsed, topic):
                return parsed
    except Exception:
        pass
    return default_metadata(topic)


def ensure_hashtag_prefix(items: list[str]) -> list[str]:
    result = []
    for item in items:
        cleaned = item.strip()
        if not cleaned:
            continue
        if not cleaned.startswith("#"):
            cleaned = "#" + cleaned.replace(" ", "")
        result.append(cleaned)
    return result


def ensure_description_hashtags(description: str, hashtags: list[str]) -> str:
    description = description.strip()
    hashtag_line = " ".join(hashtags).strip()
    if not hashtag_line:
        return description
    if hashtag_line in description:
        return description
    return f"{description}\n\n{hashtag_line}".strip()


def finalize_metadata(metadata: dict, topic: str) -> dict:
    metadata["hashtags"] = ensure_hashtag_prefix(metadata.get("hashtags", []))
    if not metadata["hashtags"]:
        fallback = default_metadata(topic)
        metadata["hashtags"] = fallback["hashtags"]
    metadata["description"] = ensure_description_hashtags(metadata.get("description", ""), metadata["hashtags"])
    return metadata


def write_text_outputs(metadata: dict, title_file: Path, description_file: Path, hashtags_file: Path, metadata_file: Path) -> None:
    title_file.write_text(metadata["title"].strip(), encoding="utf-8")
    description_file.write_text(metadata["description"].strip(), encoding="utf-8")
    hashtags_file.write_text(" ".join(metadata["hashtags"]), encoding="utf-8")
    metadata_file.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


WIKIMEDIA_UA = "youtube-bot/1.0 (thumbnail builder)"

TOPIC_THUMBNAIL_QUERIES = {
    "zodiac": "Zodiac Killer",
    "bundy": "Ted Bundy",
    "dahmer": "Jeffrey Dahmer",
    "ramirez": "Richard Ramirez night stalker",
    "aileen": "Aileen Wuornos",
    "wuornos": "Aileen Wuornos",
    "gacy": "John Wayne Gacy",
    "manson": "Charles Manson",
    "btk": "Dennis Rader BTK killer",
    "son of sam": "David Berkowitz",
    "black dahlia": "Elizabeth Short black dahlia",
    "jack the ripper": "Jack the Ripper Whitechapel",
    "ed gein": "Ed Gein",
}


def fetch_wikimedia_thumbnail_photo(topic: str) -> Image.Image | None:
    lower = topic.lower()
    query = next((v for k, v in TOPIC_THUMBNAIL_QUERIES.items() if k in lower), topic)
    try:
        import urllib.parse
        params = urllib.parse.urlencode({
            "action": "query", "format": "json",
            "generator": "search", "gsrsearch": query,
            "gsrnamespace": 6, "gsrlimit": 10,
            "prop": "imageinfo", "iiprop": "url|size",
        })
        req = Request(
            f"https://commons.wikimedia.org/w/api.php?{params}",
            headers={"User-Agent": WIKIMEDIA_UA},
        )
        with urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read())
        pages = data.get("query", {}).get("pages", {})
        best_url = ""
        best_width = 0
        for page in pages.values():
            title = str(page.get("title", "")).lower()
            if not any(ext in title for ext in (".jpg", ".jpeg", ".png")):
                continue
            infos = page.get("imageinfo") or []
            if not infos:
                continue
            url = infos[0].get("url", "")
            width = infos[0].get("width", 0)
            if url and width > best_width:
                best_url = url
                best_width = width
        if not best_url:
            return None
        img_req = Request(best_url, headers={"User-Agent": WIKIMEDIA_UA})
        with urlopen(img_req, timeout=15) as resp:
            img_bytes = resp.read()
        return Image.open(io.BytesIO(img_bytes)).convert("RGB")
    except Exception as exc:
        print(f"Wikimedia thumbnail fetch failed: {exc}")
        return None


def build_fallback_thumbnail(topic: str, thumbnail_path: Path) -> None:
    W, H = 1280, 720

    photo = fetch_wikimedia_thumbnail_photo(topic)
    if photo:
        # Crop photo to fill right half with cinematic dark tint
        scale = max(W // 2 / photo.width, H / photo.height)
        new_w = int(photo.width * scale)
        new_h = int(photo.height * scale)
        photo = photo.resize((new_w, new_h), Image.LANCZOS)
        x_off = (new_w - W // 2) // 2
        y_off = (new_h - H) // 2
        photo = photo.crop((x_off, y_off, x_off + W // 2, y_off + H))
        base = Image.new("RGB", (W, H), (8, 8, 12))
        tinted = Image.blend(photo, Image.new("RGB", (W // 2, H), (8, 8, 12)), 0.42)
        base.paste(tinted, (W // 2, 0))
        image = base
        print(f"Thumbnail: using Wikimedia photo for {topic}")
    else:
        image = Image.new("RGB", (W, H), (10, 8, 12))

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-140, -80, 520, 520), fill=(160, 20, 28, 110))
    if not photo:
        glow_draw.ellipse((760, 120, 1320, 720), fill=(120, 18, 22, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(75))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")

    draw = ImageDraw.Draw(image)
    label_font = load_font(34)
    title_font = load_font(74)
    sub_font = load_font(30)

    draw.rounded_rectangle((72, 70, 348, 132), radius=24, fill=(196, 31, 35))
    draw.text((210, 101), "TRUE CRIME FILE", font=label_font, fill=(255, 255, 255), anchor="mm")
    draw.rectangle((72, 178, 640, 184), fill=(196, 31, 35))

    words = topic.upper().split()
    line1 = " ".join(words[:3])
    line2 = " ".join(words[3:]) if len(words) > 3 else ""
    draw.text((82, 220), line1, font=title_font, fill=(245, 245, 245))
    if line2:
        draw.text((82, 308), line2, font=title_font, fill=(245, 245, 245))
    draw.text((82, 400 if line2 else 338), "DARK CASE BREAKDOWN", font=sub_font, fill=(190, 190, 196))
    draw.rounded_rectangle((82, 560, 402, 642), radius=28, fill=(18, 18, 24))
    draw.text((242, 601), "KILLER TIMELINE", font=load_font(26), fill=(255, 255, 255), anchor="mm")

    image.save(thumbnail_path)


def main() -> int:
    args = parse_args()
    script_path = Path(args.script)
    if not script_path.is_file():
        raise FileNotFoundError(f"No existe el guion: {script_path}")

    script = normalize_text(script_path.read_text(encoding="utf-8"))
    topic = args.topic.strip() or "Caso Criminal"
    metadata = finalize_metadata(build_metadata(topic, script, premium=args.premium), topic)

    write_text_outputs(
        metadata,
        title_file=Path(args.title_file),
        description_file=Path(args.description_file),
        hashtags_file=Path(args.hashtags_file),
        metadata_file=Path(args.metadata_file),
    )

    thumbnail_path = Path(args.thumbnail)
    if not thumbnail_path.is_file():
        build_fallback_thumbnail(topic, thumbnail_path)

    print(f"Title: {metadata['title']}")
    print(f"Metadata saved to: {Path(args.metadata_file)}")
    print(f"Thumbnail ready: {thumbnail_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
