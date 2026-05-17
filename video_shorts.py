import argparse
import io
import json
import os
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips, vfx
from PIL import Image, ImageDraw, ImageFilter, ImageFont


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_AUDIO = BASE_DIR / "audio.mp3"
DEFAULT_TIMESTAMPS = BASE_DIR / "timestamps.json"
DEFAULT_PROMPTS = BASE_DIR / "image_prompts.json"
DEFAULT_OUTPUT = BASE_DIR / "short_video.mp4"
DEFAULT_TOPIC = "True Crime Short"
GENERATED_IMAGES_DIR = BASE_DIR / "generated_images"
DEFAULT_BACKGROUND_VIDEO = BASE_DIR / "runway_clip.mp4"
VIDEO_SIZE = (1080, 1920)
INTRO_DURATION = 1.1
EXPORT_FPS = 24
ACCENT_RED = (196, 31, 35)
KARAOKE_FONTSIZE = 88
KARAOKE_STROKE = 5
KARAOKE_Y_RATIO = 0.74
TEXT_WHITE = (246, 246, 246)
TEXT_MUTED = (196, 196, 204)
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_HEADERS = {"User-Agent": "youtube-bot/1.0 (shorts renderer)"}
FONT_CANDIDATES = [
    "C:/Windows/Fonts/bahnschrift.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/corbelb.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
]

TOPIC_IMAGE_QUERIES = {
    "zodiac": ["Zodiac Killer", "Zodiac killer letters", "Lake Berryessa attack"],
    "ted bundy": ["Ted Bundy", "Theodore Bundy", "Bundy trial"],
    "jack the ripper": ["Jack the Ripper", "Whitechapel murders"],
    "jeffrey dahmer": ["Jeffrey Dahmer"],
}

TOPIC_IMAGE_URLS = {
    "ted bundy": [
        "https://upload.wikimedia.org/wikipedia/commons/c/cc/Ted_Bundy_headshot.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/5/51/Ted_Bundy_1988_mugshot.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/a/ab/Ted_Bundy_HS_Yearbook.jpeg",
        "https://upload.wikimedia.org/wikipedia/commons/b/b4/Bundy_FLA_8179.jpeg",
        "https://upload.wikimedia.org/wikipedia/commons/d/dd/Ted_Bundy_in_court.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/3/34/Ted_Bundy_Sentencing_Document.jpg",
        "https://upload.wikimedia.org/wikipedia/commons/8/8c/Dental_evidence_ted_bundy.jpeg",
        "https://upload.wikimedia.org/wikipedia/commons/f/f1/1968_Volkswagen_Beetle_%2814361020315%29.jpg",
    ],
}

TOPIC_IMAGE_FILES = {
    "zodiac": {
        "cipher": [
            "June 26 1970 Zodiac letter.jpg",
            "June 26 1970 Zodiac letter (cropped).jpg",
        ],
        "letter": [
            "June 26 1970 Zodiac letter.jpg",
            "Images-ch9 letter.jpg",
        ],
        "sketch": [
            "Zodiac-Killer.jpg",
            "Zodiac killer from Paul Stine murder.png",
        ],
        "scene": [
            "Lake Berryessa Sketch of the Zodiac Killer as described by 3 coeds sunbathing that day.jpg",
            "Zodiac killer from Paul Stine murder.png",
        ],
        "fallback": [
            "Zodiac-Killer.jpg",
            "June 26 1970 Zodiac letter.jpg",
            "Zodiac killer from Paul Stine murder.png",
            "Lake Berryessa Sketch of the Zodiac Killer as described by 3 coeds sunbathing that day.jpg",
            "Images-ch9 letter.jpg",
        ],
    }
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render a vertical true crime short.")
    parser.add_argument("--audio", default=str(DEFAULT_AUDIO))
    parser.add_argument("--timestamps", default=str(DEFAULT_TIMESTAMPS))
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS))
    parser.add_argument("--images-dir", default=str(GENERATED_IMAGES_DIR))
    parser.add_argument("--background-video", nargs="*", default=[])
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    parser.add_argument("--single-image", action="store_true", help="Use one main image through the whole short.")
    return parser.parse_args()


def load_font(size: int):
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def draw_text_with_shadow(draw, position, text, *, font, fill, anchor="lt", shadow_offset=(4, 4), shadow_fill=(0, 0, 0, 180)):
    shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
    draw.text(shadow_pos, text, font=font, fill=shadow_fill, anchor=anchor)
    draw.text(position, text, font=font, fill=fill, anchor=anchor)


def make_base_frame() -> Image.Image:
    frame = Image.new("RGB", VIDEO_SIZE, (8, 8, 12))
    width, height = VIDEO_SIZE
    pixels = frame.load()
    for y in range(height):
        for x in range(width):
            vertical = y / height
            red = int(10 + (55 * (1.0 - vertical)))
            green = int(8 + (10 * vertical))
            blue = int(12 + (25 * vertical))
            pixels[x, y] = (min(red, 255), min(green, 255), min(blue, 255))

    glow = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-120, -40, 700, 900), fill=(145, 16, 22, 90))
    glow_draw.ellipse((420, 760, 1160, 1860), fill=(120, 18, 22, 70))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(frame.convert("RGBA"), glow).convert("RGB")


def load_generated_images(images_dir: Path, count: int) -> list[Image.Image]:
    if not images_dir.is_dir():
        return []
    images = []
    for path in sorted(images_dir.iterdir()):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            continue
        try:
            images.append(Image.open(path).convert("RGB"))
        except Exception:
            continue
        if len(images) >= count:
            break
    return images


def build_wikimedia_queries(topic: str) -> list[str]:
    normalized = topic.lower().strip()
    for key, queries in TOPIC_IMAGE_QUERIES.items():
        if key in normalized:
            return queries
    cleaned = topic.replace("|", " ").replace(":", " ")
    return [cleaned, f'"{cleaned}" crime']


def fetch_wikimedia_images(topic: str, count: int) -> list[Image.Image]:
    normalized = topic.lower().strip()
    for key, urls in TOPIC_IMAGE_URLS.items():
        if key in normalized:
            images = []
            for url in urls[:count]:
                try:
                    r = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=15)
                    r.raise_for_status()
                    images.append(Image.open(io.BytesIO(r.content)).convert("RGB"))
                except Exception:
                    continue
            if images:
                return images

    queries = build_wikimedia_queries(topic)
    urls = []
    seen = set()
    for query in queries:
        try:
            response = requests.get(
                WIKIMEDIA_API,
                headers=WIKIMEDIA_HEADERS,
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrnamespace": 6,
                    "gsrlimit": count,
                    "prop": "imageinfo",
                    "iiprop": "url",
                },
                timeout=12,
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            for page in pages.values():
                infos = page.get("imageinfo") or []
                if not infos:
                    continue
                url = infos[0].get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    urls.append(url)
                if len(urls) >= count:
                    break
        except Exception:
            continue
        if len(urls) >= count:
            break

    images = []
    for url in urls:
        try:
            r = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=15)
            r.raise_for_status()
            images.append(Image.open(io.BytesIO(r.content)).convert("RGB"))
        except Exception:
            continue
    return images


def fetch_images_from_file_titles(file_titles: list[str]) -> list[Image.Image]:
    images = []
    for title in file_titles:
        try:
            response = requests.get(
                WIKIMEDIA_API,
                headers=WIKIMEDIA_HEADERS,
                params={
                    "action": "query",
                    "format": "json",
                    "titles": f"File:{title}",
                    "prop": "imageinfo",
                    "iiprop": "url",
                },
                timeout=12,
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            url = ""
            for page in pages.values():
                infos = page.get("imageinfo") or []
                if infos:
                    url = infos[0].get("url", "")
                    break
            if not url:
                continue
            r = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=15)
            r.raise_for_status()
            images.append(Image.open(io.BytesIO(r.content)).convert("RGB"))
        except Exception:
            continue
    return images


def select_images_for_beats(topic: str, prompt_timeline: list[dict]) -> list[Image.Image]:
    normalized = topic.lower().strip()
    if "ted bundy" in normalized:
        beat_specific_urls = []
        for beat in prompt_timeline:
            text = f"{beat.get('beat_type', '')} {beat.get('narration_text', '')}".lower()
            if "volkswagen" in text or "beetle" in text or "passenger seat" in text:
                beat_specific_urls.append("https://upload.wikimedia.org/wikipedia/commons/f/f1/1968_Volkswagen_Beetle_%2814361020315%29.jpg")
            elif "court" in text or "electric chair" in text or "legacy" in text:
                beat_specific_urls.append("https://upload.wikimedia.org/wikipedia/commons/d/dd/Ted_Bundy_in_court.jpg")
            elif "body count" in text or "victims" in text or "died with him" in text:
                beat_specific_urls.append("https://upload.wikimedia.org/wikipedia/commons/8/8c/Dental_evidence_ted_bundy.jpeg")
            elif "smile" in text or "charm" in text or "harmless" in text:
                beat_specific_urls.append("https://upload.wikimedia.org/wikipedia/commons/c/cc/Ted_Bundy_headshot.jpg")
            else:
                beat_specific_urls.append("")

        fallback_urls = TOPIC_IMAGE_URLS["ted bundy"]
    elif "zodiac" in normalized:
        zodiac_files = TOPIC_IMAGE_FILES["zodiac"]
        beat_specific_urls = []
        for beat in prompt_timeline:
            text = f"{beat.get('beat_type', '')} {beat.get('narration_text', '')}".lower()
            if "cipher" in text or "code" in text or "symbol" in text:
                beat_specific_urls.append("cipher")
            elif "letter" in text or "newspaper" in text or "message" in text or "taunt" in text:
                beat_specific_urls.append("letter")
            elif "taxi" in text or "cab" in text or "driver" in text or "street" in text:
                beat_specific_urls.append("sketch")
            elif "park" in text or "lake" in text or "night" in text or "attack" in text:
                beat_specific_urls.append("scene")
            else:
                beat_specific_urls.append("")

        chosen_titles = []
        used = set()
        fallback_titles = list(zodiac_files["fallback"])

        for bucket in beat_specific_urls:
            title = ""
            if bucket:
                for candidate in zodiac_files.get(bucket, []):
                    if candidate not in used:
                        title = candidate
                        break
            while (not title) and fallback_titles:
                candidate = fallback_titles.pop(0)
                if candidate not in used:
                    title = candidate
                    break
            if title:
                chosen_titles.append(title)
                used.add(title)

        return fetch_images_from_file_titles(chosen_titles)
    else:
        return []

    chosen_urls = []
    used = set()
    fallback_index = 0

    for candidate in beat_specific_urls:
        url = candidate if candidate and candidate not in used else ""
        while (not url) and fallback_index < len(fallback_urls):
            maybe = fallback_urls[fallback_index]
            fallback_index += 1
            if maybe not in used:
                url = maybe
                break
        if url:
            chosen_urls.append(url)
            used.add(url)

    images = []
    for url in chosen_urls:
        try:
            r = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=15)
            r.raise_for_status()
            images.append(Image.open(io.BytesIO(r.content)).convert("RGB"))
        except Exception:
            continue
    return images


def fit_vertical(image: Image.Image) -> Image.Image:
    img_ratio = image.width / image.height
    target_ratio = VIDEO_SIZE[0] / VIDEO_SIZE[1]
    if img_ratio > target_ratio:
        new_height = VIDEO_SIZE[1]
        new_width = int(new_height * img_ratio)
    else:
        new_width = VIDEO_SIZE[0]
        new_height = int(new_width / img_ratio)
    image = image.resize((new_width, new_height), Image.LANCZOS)
    x = (new_width - VIDEO_SIZE[0]) // 2
    y = (new_height - VIDEO_SIZE[1]) // 2
    return image.crop((x, y, x + VIDEO_SIZE[0], y + VIDEO_SIZE[1]))


def load_prompt_timeline(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in data if isinstance(item, dict) and "start" in item and "end" in item]


def make_story_frame(image: Image.Image | None, base_frame: Image.Image) -> np.ndarray:
    if image is None:
        frame = base_frame.copy()
    else:
        fitted = fit_vertical(image)
        fitted = Image.blend(fitted, Image.new("RGB", VIDEO_SIZE, (0, 0, 0)), 0.38)
        frame = Image.blend(fitted, base_frame, 0.25)

    overlay = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((34, 34, VIDEO_SIZE[0] - 34, VIDEO_SIZE[1] - 34), outline=(255, 255, 255, 18), width=2)
    return np.array(Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB"))


def build_beat_clip(frame: np.ndarray, start: float, duration: float, index: int) -> ImageClip:
    direction = -1 if index % 2 else 1

    def scale_at(t: float) -> float:
        progress = min(max(t / max(duration, 0.1), 0.0), 1.0)
        return 1.04 + (0.08 * progress)

    def position_at(t: float) -> tuple[float, float]:
        progress = min(max(t / max(duration, 0.1), 0.0), 1.0)
        return (-20 + direction * 16 * progress, -18 + 16 * progress)

    return (
        ImageClip(frame)
        .set_start(start)
        .set_duration(duration)
        .resize(lambda t: scale_at(t))
        .set_position(lambda t: position_at(t))
        .fadein(0.08)
        .fadeout(0.08)
    )


def fetch_best_wikimedia_portrait(topic: str) -> Image.Image | None:
    """Fetches the single highest-resolution portrait from Wikimedia for cinematic single-image mode."""
    import urllib.parse
    normalized = topic.lower().strip()
    queries = build_wikimedia_queries(topic)
    best_image = None
    best_pixels = 0

    for query in queries:
        try:
            response = requests.get(
                WIKIMEDIA_API,
                headers=WIKIMEDIA_HEADERS,
                params={
                    "action": "query", "format": "json",
                    "generator": "search", "gsrsearch": query,
                    "gsrnamespace": 6, "gsrlimit": 12,
                    "prop": "imageinfo", "iiprop": "url|size",
                },
                timeout=12,
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            for page in pages.values():
                title = str(page.get("title", "")).lower()
                if not any(ext in title for ext in (".jpg", ".jpeg", ".png")):
                    continue
                infos = page.get("imageinfo") or []
                if not infos:
                    continue
                url = infos[0].get("url", "")
                w = int(infos[0].get("width", 0))
                h = int(infos[0].get("height", 0))
                if not url or w * h < best_pixels:
                    continue
                # Prefer roughly portrait or square photos for vertical format
                aspect = h / w if w else 0
                if aspect < 0.6:
                    continue
                try:
                    r = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=20)
                    r.raise_for_status()
                    img = Image.open(io.BytesIO(r.content)).convert("RGB")
                    if img.width * img.height > best_pixels:
                        best_image = img
                        best_pixels = img.width * img.height
                except Exception:
                    continue
        except Exception:
            continue

    return best_image


def make_horror_story_frame(image: Image.Image) -> np.ndarray:
    """Single-image dramatic background: dark vignette, red tint, film grain, contrast boost."""
    fitted = fit_vertical(image)

    # Boost contrast and slightly desaturate
    from PIL import ImageEnhance
    fitted = ImageEnhance.Contrast(fitted).enhance(1.18)
    fitted = ImageEnhance.Color(fitted).enhance(0.72)
    fitted = ImageEnhance.Brightness(fitted).enhance(0.88)

    # Heavy dark overlay for subtitle readability
    dark = Image.new("RGB", VIDEO_SIZE, (0, 0, 0))
    fitted = Image.blend(fitted, dark, 0.42)

    # Red atmospheric glow on edges
    glow = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-200, -200, 600, 800), fill=(140, 18, 22, 60))
    glow_draw.ellipse((480, 1300, 1280, 2100), fill=(110, 16, 20, 50))
    glow = glow.filter(ImageFilter.GaussianBlur(110))
    fitted = Image.alpha_composite(fitted.convert("RGBA"), glow).convert("RGB")

    # Strong vignette
    vignette = Image.new("L", VIDEO_SIZE, 0)
    vignette_draw = ImageDraw.Draw(vignette)
    vignette_draw.ellipse((-180, -260, VIDEO_SIZE[0] + 180, VIDEO_SIZE[1] + 260), fill=235)
    vignette = vignette.filter(ImageFilter.GaussianBlur(140))
    black = Image.new("RGB", VIDEO_SIZE, (0, 0, 0))
    fitted = Image.composite(fitted, black, vignette)

    # Subtle film grain texture
    rng = np.random.default_rng(7)
    grain = rng.normal(0, 6, (VIDEO_SIZE[1], VIDEO_SIZE[0], 3)).astype(np.int16)
    arr = np.array(fitted).astype(np.int16) + grain
    arr = np.clip(arr, 0, 255).astype(np.uint8)

    return arr


def build_single_image_background(image: Image.Image, total_duration: float) -> ImageClip:
    """ONE static frame with continuous slow zoom — viral true crime Shorts format."""
    frame = make_horror_story_frame(image)

    def scale_at(t: float) -> float:
        progress = min(max(t / max(total_duration, 0.1), 0.0), 1.0)
        return 1.0 + (0.085 * progress)

    def position_at(t: float) -> tuple[float, float]:
        progress = min(max(t / max(total_duration, 0.1), 0.0), 1.0)
        return (-4 * progress, -10 * progress)

    return (
        ImageClip(frame)
        .set_duration(total_duration)
        .resize(scale_at)
        .set_position(position_at)
    )


def build_background(total_duration: float, images: list[Image.Image], prompt_timeline: list[dict]) -> ImageClip | CompositeVideoClip:
    base_frame = make_base_frame()
    if not images:
        return ImageClip(np.array(base_frame)).set_duration(total_duration)

    clips = []
    fallback_frame = make_story_frame(images[0], base_frame)
    clips.append(build_beat_clip(fallback_frame, 0.0, total_duration, 0))

    for index, beat in enumerate(prompt_timeline):
        start = INTRO_DURATION + float(beat.get("start", 0.0))
        end = INTRO_DURATION + float(beat.get("end", 0.0))
        duration = max(min(end - start, total_duration - start), 1.0)
        frame = make_story_frame(images[index % len(images)], base_frame)
        clips.append(build_beat_clip(frame, start, duration, index))

    return CompositeVideoClip(clips, size=VIDEO_SIZE).set_duration(total_duration)


def fit_background_video_clip(path: Path, duration: float) -> VideoFileClip:
    base = VideoFileClip(str(path)).without_audio()
    base_duration = base.duration
    visible_duration = min(base_duration, duration)
    animated = base.subclip(0, visible_duration)

    scale = max(VIDEO_SIZE[0] / animated.w, VIDEO_SIZE[1] / animated.h)
    fitted = animated.resize(scale)
    x1 = max((fitted.w - VIDEO_SIZE[0]) / 2, 0)
    y1 = max((fitted.h - VIDEO_SIZE[1]) / 2, 0)
    fitted = fitted.crop(x1=x1, y1=y1, width=VIDEO_SIZE[0], height=VIDEO_SIZE[1]).fx(vfx.colorx, 0.86)

    if visible_duration >= duration:
        return fitted

    last_frame = fitted.get_frame(max(visible_duration - 0.05, 0.0))
    hold_duration = max(duration - visible_duration, 0.0)
    hold = (
        ImageClip(last_frame)
        .set_duration(hold_duration)
        .resize(lambda t: 1.0 + (0.045 * min(max(t / max(hold_duration, 0.1), 0.0), 1.0)))
        .set_position(lambda t: (-8 * min(max(t / max(hold_duration, 0.1), 0.0), 1.0), -12 * min(max(t / max(hold_duration, 0.1), 0.0), 1.0)))
        .fadein(0.08)
        .fadeout(0.08)
    )
    return concatenate_videoclips([fitted, hold], method="compose")


def build_background_video(paths: list[Path], total_duration: float) -> CompositeVideoClip:
    valid_paths = [path for path in paths if path.is_file()]
    if not valid_paths:
        raise FileNotFoundError("No valid background video paths provided.")

    if len(valid_paths) == 1:
        fitted = fit_background_video_clip(valid_paths[0], total_duration)
        tint = ImageClip(np.array(make_base_frame())).set_duration(total_duration).set_opacity(0.10)
        return CompositeVideoClip([fitted, tint], size=VIDEO_SIZE).set_duration(total_duration)

    segment_duration = total_duration / len(valid_paths)
    clips = []
    current_start = 0.0
    for path in valid_paths:
        clip = fit_background_video_clip(path, segment_duration).set_start(current_start)
        clips.append(clip)
        current_start += segment_duration

    tint = ImageClip(np.array(make_base_frame())).set_duration(total_duration).set_opacity(0.10)
    return CompositeVideoClip(clips + [tint], size=VIDEO_SIZE).set_duration(total_duration)


def make_intro_clip(topic: str) -> ImageClip:
    image = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    label_font = load_font(28)
    title_font = load_font(68)
    draw.rounded_rectangle((94, 140, 340, 204), radius=24, fill=(*ACCENT_RED, 235))
    draw_text_with_shadow(draw, (217, 172), "TRUE CRIME", font=label_font, fill=(255, 255, 255, 255), anchor="mm")
    draw_text_with_shadow(draw, (VIDEO_SIZE[0] // 2, 360), topic.upper(), font=title_font, fill=(*TEXT_WHITE, 255), anchor="mm")
    draw_text_with_shadow(draw, (VIDEO_SIZE[0] // 2, 1540), "KILLER TIMELINE", font=load_font(30), fill=(*TEXT_MUTED, 255), anchor="mm")
    return ImageClip(np.array(image)).set_duration(INTRO_DURATION).fadein(0.12).fadeout(0.12)


def _draw_stroked_text(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill: tuple, stroke: int) -> None:
    offsets = [(-stroke, 0), (stroke, 0), (0, -stroke), (0, stroke),
               (-stroke, -stroke), (stroke, -stroke), (-stroke, stroke), (stroke, stroke)]
    for dx, dy in offsets:
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 255), anchor="mm")
    draw.text((x, y), text, font=font, fill=fill, anchor="mm")


def make_karaoke_word_clips(word_boundaries: list[dict]) -> list[ImageClip]:
    font = load_font(KARAOKE_FONTSIZE)
    clips = []
    center_x = VIDEO_SIZE[0] // 2
    center_y = int(VIDEO_SIZE[1] * KARAOKE_Y_RATIO)

    for wb in word_boundaries:
        word = wb.get("word", "").strip()
        if not word:
            continue
        start = float(wb["start"])
        duration = max(float(wb["duration"]), 0.05)
        end = start + duration

        label = word.upper()
        dummy = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        bbox = dummy.textbbox((0, 0), label, font=font, anchor="mm")
        text_w = bbox[2] - bbox[0] + KARAOKE_STROKE * 2 + 8
        text_h = bbox[3] - bbox[1] + KARAOKE_STROKE * 2 + 8
        img_w = max(text_w + 24, 60)
        img_h = max(text_h + 16, 40)

        image = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        tx, ty = img_w // 2, img_h // 2
        _draw_stroked_text(draw, tx, ty, label, font, (*TEXT_WHITE, 255), KARAOKE_STROKE)

        pos_x = center_x - img_w // 2
        pos_y = center_y - img_h // 2

        clips.append(
            ImageClip(np.array(image))
            .set_start(INTRO_DURATION + start)
            .set_end(INTRO_DURATION + end)
            .set_position((pos_x, pos_y))
            .fadein(0.02)
            .fadeout(0.02)
        )
    return clips


def make_cta_clip(start: float, duration: float) -> ImageClip:
    image = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((138, 1680, 942, 1774), radius=34, fill=(*ACCENT_RED, 240))
    draw_text_with_shadow(draw, (540, 1727), "SUBSCRIBE FOR MORE", font=load_font(34), fill=(255, 255, 255, 255), anchor="mm")
    return ImageClip(np.array(image)).set_start(start).set_duration(duration).fadein(0.08).fadeout(0.08)


def resolve_music_path() -> Path | None:
    for candidate in (BASE_DIR / "music.wav", BASE_DIR / "music.mp3"):
        if candidate.is_file():
            return candidate
    return None


def mix_audio(voice: AudioFileClip, music_path: Path | None, total_duration: float):
    voice = voice.set_start(INTRO_DURATION).volumex(1.1)
    if not music_path or not music_path.is_file():
        return voice
    music = AudioFileClip(str(music_path)).volumex(0.34)
    if music.duration < total_duration:
        loops = int(total_duration / music.duration) + 1
        from moviepy.audio.AudioClip import concatenate_audioclips
        music = concatenate_audioclips([music] * loops)
    music = music.subclip(0, total_duration).audio_fadein(0.5).audio_fadeout(0.6)
    return CompositeAudioClip([music, voice])


def build_short(
    audio_path: Path,
    timestamps_path: Path,
    prompts_path: Path,
    output_path: Path,
    topic: str,
    images_dir: Path,
    background_video_paths: list[Path],
    single_image: bool = False,
) -> None:
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    audio = AudioFileClip(str(audio_path))
    total_duration = audio.duration + INTRO_DURATION
    word_boundaries = json.loads(timestamps_path.read_text(encoding="utf-8")) if timestamps_path.is_file() else []
    prompt_timeline = load_prompt_timeline(prompts_path)

    valid_backgrounds = [path for path in background_video_paths if path and path.is_file()]
    if valid_backgrounds:
        background = build_background_video(valid_backgrounds, total_duration)
    elif single_image:
        # Single-image mode: ONE highest-resolution portrait, cinematic horror treatment
        portrait = fetch_best_wikimedia_portrait(topic)
        if portrait is None:
            local = load_generated_images(images_dir, 1)
            if local:
                portrait = local[0]
            else:
                fallback = fetch_wikimedia_images(topic, 1)
                portrait = fallback[0] if fallback else None
        if portrait is None:
            background = ImageClip(np.array(make_base_frame())).set_duration(total_duration)
        else:
            print(f"Single-image mode: portrait {portrait.size}")
            background = build_single_image_background(portrait, total_duration)
    else:
        images = load_generated_images(images_dir, max(len(prompt_timeline), 1))
        if not images:
            images = select_images_for_beats(topic, prompt_timeline)
        if not images:
            images = fetch_wikimedia_images(topic, max(len(prompt_timeline), 3))
        background = build_background(total_duration, images, prompt_timeline)
    intro = make_intro_clip(topic)
    subtitle_clips = make_karaoke_word_clips(word_boundaries)
    cta_start = max(total_duration - 2.6, 2.2)
    cta = make_cta_clip(cta_start, total_duration - cta_start)
    final_audio = mix_audio(audio, resolve_music_path(), total_duration)

    video = CompositeVideoClip([background, intro] + subtitle_clips + [cta], size=VIDEO_SIZE).set_audio(final_audio)
    video.write_videofile(
        str(output_path),
        fps=EXPORT_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger=None,
    )
    print(f"Short saved to: {output_path}")


def main() -> int:
    args = parse_args()
    build_short(
        audio_path=Path(args.audio),
        timestamps_path=Path(args.timestamps),
        prompts_path=Path(args.prompts),
        output_path=Path(args.output),
        topic=args.topic,
        images_dir=Path(args.images_dir),
        background_video_paths=[Path(item) for item in args.background_video] if args.background_video else [DEFAULT_BACKGROUND_VIDEO],
        single_image=args.single_image,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
