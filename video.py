import argparse
import io
import json
import os
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)
from PIL import Image, ImageDraw, ImageFilter, ImageFont


load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_AUDIO = BASE_DIR / "audio.mp3"
DEFAULT_TIMESTAMPS = BASE_DIR / "timestamps.json"
DEFAULT_OUTPUT = BASE_DIR / "video.mp4"
DEFAULT_TOPIC = "Crime Case"
GENERATED_IMAGES_DIR = BASE_DIR / "generated_images"
ANIMATED_SCENES_DIR = BASE_DIR / "animated_scenes"
DEFAULT_PROMPTS = BASE_DIR / "image_prompts.json"
WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
WIKIMEDIA_HEADERS = {
    "User-Agent": "youtube-bot/1.0 (local automation test)",
}

VIDEO_SIZE = (1920, 1080)
TITLE_DURATION = 3.0
PROLOGUE_DURATION = 3.2
NARRATION_OFFSET = TITLE_DURATION + PROLOGUE_DURATION
IMAGE_DURATION = 4.0
WORDS_PER_SUBTITLE = 5
SUBTITLE_FONTSIZE = 62
TITLE_FONTSIZE = 92
LABEL_FONTSIZE = 32
WATERMARK_FONTSIZE = 34
WATERMARK_PADDING = 32
WATERMARK_TEXT = "KILLER TIMELINE"
MUSIC_VOLUME = 0.38
EXPORT_FPS = 30
SUBTITLE_BG = (8, 8, 12, 210)
ACCENT_RED = (196, 31, 35)
TEXT_WHITE = (245, 245, 245)
TEXT_MUTED = (185, 185, 193)
CTA_BG = (18, 18, 24, 228)
CTA_START_OFFSET = 14.0
CTA_DURATION = 6.0
CTA_END_OFFSET = 16.0

FONT_CANDIDATES = [
    "C:/Windows/Fonts/bahnschrift.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/corbelb.ttf",
    "C:/Windows/Fonts/georgiab.ttf",
    "C:/Windows/Fonts/trebucbd.ttf",
    "C:/Windows/Fonts/verdanab.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]

TOPIC_IMAGE_QUERIES = {
    "zodiac": ["Zodiac Killer", "Zodiac killer letters", "Lake Berryessa attack"],
    "ted bundy": ["Ted Bundy", "Theodore Bundy", "Bundy trial"],
    "jack the ripper": ["Jack the Ripper", "Whitechapel murders"],
    "jeffrey dahmer": ["Jeffrey Dahmer"],
    "btk": ["Dennis Rader", "BTK Killer"],
    "richard ramirez": ["Richard Ramirez", "Night Stalker"],
    "john wayne gacy": ["John Wayne Gacy"],
    "charles manson": ["Charles Manson", "Manson Family"],
    "ed gein": ["Ed Gein"],
    "son of sam": ["David Berkowitz", "Son of Sam"],
    "black dahlia": ["Black Dahlia", "Elizabeth Short"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render an MP4 with synced subtitles.")
    parser.add_argument("--audio", default=str(DEFAULT_AUDIO))
    parser.add_argument("--timestamps", default=str(DEFAULT_TIMESTAMPS))
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--topic", default=DEFAULT_TOPIC)
    return parser.parse_args()


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def rounded_rectangle(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: tuple[int, ...]) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def draw_text_with_shadow(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    *,
    font: ImageFont.ImageFont,
    fill: tuple[int, ...],
    anchor: str = "lt",
    shadow_offset: tuple[int, int] = (3, 3),
    shadow_fill: tuple[int, ...] = (0, 0, 0, 170),
) -> None:
    shadow_pos = (position[0] + shadow_offset[0], position[1] + shadow_offset[1])
    draw.text(shadow_pos, text, font=font, fill=shadow_fill, anchor=anchor)
    draw.text(position, text, font=font, fill=fill, anchor=anchor)


def make_cinematic_base_frame() -> Image.Image:
    width, height = VIDEO_SIZE
    frame = Image.new("RGB", VIDEO_SIZE, (8, 8, 12))
    pixels = frame.load()

    for y in range(height):
        for x in range(width):
            vertical = y / height
            horizontal = x / width
            red = int(10 + (18 * (1.0 - vertical)) + (32 * abs(0.5 - horizontal)))
            green = int(8 + (10 * vertical))
            blue = int(12 + (26 * vertical))
            pixels[x, y] = (min(red, 255), min(green, 255), min(blue, 255))

    glow = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((-220, -80, 520, 560), fill=(140, 18, 22, 90))
    glow_draw.ellipse((width - 420, 40, width + 120, 440), fill=(120, 18, 22, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    frame = Image.alpha_composite(frame.convert("RGBA"), glow).convert("RGB")

    vignette = Image.new("L", VIDEO_SIZE, 0)
    vignette_draw = ImageDraw.Draw(vignette)
    vignette_draw.ellipse((-160, -120, width + 160, height + 120), fill=210)
    vignette = vignette.filter(ImageFilter.GaussianBlur(100))
    dark = Image.new("RGB", VIDEO_SIZE, (0, 0, 0))
    frame = Image.composite(frame, dark, vignette)

    lines = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    lines_draw = ImageDraw.Draw(lines)
    for y in range(0, height, 6):
        lines_draw.line((0, y, width, y), fill=(255, 255, 255, 8), width=1)
    frame = Image.alpha_composite(frame.convert("RGBA"), lines).convert("RGB")
    return frame


def fetch_images(topic: str, count: int = 6) -> list[Image.Image]:
    local_images = load_generated_images(GENERATED_IMAGES_DIR, count)
    if local_images:
        print(f"AI images found: {len(local_images)}")
        return local_images

    commons_images = fetch_wikimedia_images(topic, count)
    if commons_images:
        print(f"Wikimedia images found: {len(commons_images)}")
        return commons_images

    api_key = os.getenv("PEXELS_API_KEY", "").strip()
    if not api_key:
        return []

    headers = {"Authorization": api_key}
    params = {
        "query": topic.split("|")[0].strip(),
        "per_page": count,
        "orientation": "landscape",
    }
    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers=headers,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        photos = response.json().get("photos", [])
        images: list[Image.Image] = []
        for photo in photos:
            image_response = requests.get(photo["src"]["large2x"], timeout=10)
            image_response.raise_for_status()
            image = Image.open(io.BytesIO(image_response.content)).convert("RGB")
            images.append(image)
        print(f"Downloaded images: {len(images)}")
        return images
    except Exception as exc:
        print(f"Could not download images: {exc}")
        return []


def fetch_wikimedia_images(topic: str, count: int) -> list[Image.Image]:
    queries = build_wikimedia_queries(topic)
    collected_urls: list[str] = []
    seen: set[str] = set()

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
                title = str(page.get("title", "")).lower()
                if not any(ext in title for ext in (".jpg", ".jpeg", ".png", ".webp")):
                    continue
                infos = page.get("imageinfo") or []
                if not infos:
                    continue
                url = infos[0].get("url", "")
                if not url or url in seen:
                    continue
                seen.add(url)
                collected_urls.append(url)
                if len(collected_urls) >= count:
                    break
        except Exception:
            continue
        if len(collected_urls) >= count:
            break

    images: list[Image.Image] = []
    for url in collected_urls:
        try:
            image_response = requests.get(url, headers=WIKIMEDIA_HEADERS, timeout=15)
            image_response.raise_for_status()
            images.append(Image.open(io.BytesIO(image_response.content)).convert("RGB"))
        except Exception:
            continue
    return images


def build_wikimedia_queries(topic: str) -> list[str]:
    normalized = topic.lower().strip()
    for key, queries in TOPIC_IMAGE_QUERIES.items():
        if key in normalized:
            return queries

    cleaned = topic.replace("|", " ").replace(":", " ")
    return [cleaned, f'"{cleaned}" crime', f'"{cleaned}" case']


def load_animated_clips(scenes_dir: Path) -> list[VideoFileClip]:
    if not scenes_dir.is_dir():
        return []
    clips = []
    for path in sorted(scenes_dir.iterdir()):
        if path.suffix.lower() == ".mp4":
            try:
                clips.append(VideoFileClip(str(path)).resize(VIDEO_SIZE))
            except Exception as exc:
                print(f"Could not load animated clip {path.name}: {exc}")
    return clips


def build_background_from_animated_clips(clips: list[VideoFileClip], total_duration: float) -> VideoFileClip:
    combined = concatenate_videoclips(clips, method="compose")
    if combined.duration < total_duration:
        loops = int(total_duration / combined.duration) + 1
        combined = concatenate_videoclips([combined] * loops, method="compose")
    return combined.subclip(0, total_duration)


def load_generated_images(images_dir: Path, count: int) -> list[Image.Image]:
    if not images_dir.is_dir():
        return []

    images: list[Image.Image] = []
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


def fit_image(image: Image.Image) -> Image.Image:
    img_ratio = image.width / image.height
    video_ratio = VIDEO_SIZE[0] / VIDEO_SIZE[1]
    if img_ratio > video_ratio:
        new_height = VIDEO_SIZE[1]
        new_width = int(new_height * img_ratio)
    else:
        new_width = VIDEO_SIZE[0]
        new_height = int(new_width / img_ratio)

    image = image.resize((new_width, new_height), Image.LANCZOS)
    x = (new_width - VIDEO_SIZE[0]) // 2
    y = (new_height - VIDEO_SIZE[1]) // 2
    return image.crop((x, y, x + VIDEO_SIZE[0], y + VIDEO_SIZE[1]))


def make_story_frame(image: Image.Image | None, base_frame: Image.Image) -> np.ndarray:
    if image is None:
        frame = base_frame.copy()
    else:
        fitted = fit_image(image)
        fitted = Image.blend(fitted, Image.new("RGB", VIDEO_SIZE, (0, 0, 0)), 0.45)
        frame = Image.blend(fitted, base_frame, 0.35)

    overlay = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rectangle((38, 38, VIDEO_SIZE[0] - 38, VIDEO_SIZE[1] - 38), outline=(255, 255, 255, 18), width=2)
    draw.rectangle((54, 54, VIDEO_SIZE[0] - 54, VIDEO_SIZE[1] - 54), outline=(196, 31, 35, 26), width=1)
    frame = Image.alpha_composite(frame.convert("RGBA"), overlay).convert("RGB")
    return np.array(frame)


def build_animated_image_clip(frame: np.ndarray, duration: float, start: float, index: int) -> ImageClip:
    zoom_start = 1.05 + (0.01 * (index % 3))
    zoom_delta = 0.05
    direction = -1 if index % 2 else 1

    def scale_at(t: float) -> float:
        progress = min(max(t / max(duration, 0.1), 0.0), 1.0)
        return zoom_start + (zoom_delta * progress)

    def position_at(t: float) -> tuple[float, float]:
        progress = min(max(t / max(duration, 0.1), 0.0), 1.0)
        drift_x = direction * (26 * progress)
        drift_y = -12 + (18 * progress)
        return (-36 + drift_x, drift_y)

    return (
        ImageClip(frame)
        .set_start(start)
        .set_duration(duration)
        .resize(lambda t: scale_at(t))
        .set_position(lambda t: position_at(t))
        .fadein(0.25)
        .fadeout(0.30)
    )


def load_prompt_timeline(prompts_path: Path) -> list[dict]:
    if not prompts_path.is_file():
        return []
    try:
        prompts = json.loads(prompts_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [item for item in prompts if isinstance(item, dict) and "start" in item and "end" in item]


def build_background(total_duration: float, images: list[Image.Image], prompt_timeline: list[dict]) -> ImageClip | CompositeVideoClip:
    base_frame = make_cinematic_base_frame()
    if not images:
        return (
            ImageClip(np.array(base_frame))
            .set_duration(total_duration)
            .resize(lambda t: 1.04 + (0.04 * (t / max(total_duration, 0.1))))
            .set_position(lambda t: (-18 + (12 * (t / max(total_duration, 0.1))), -10))
        )

    clips = []
    if prompt_timeline:
        for index, beat in enumerate(prompt_timeline):
            image = images[index % len(images)]
            start = NARRATION_OFFSET + float(beat.get("start", 0.0))
            end = NARRATION_OFFSET + float(beat.get("end", 0.0))
            duration = max(min(end - start, total_duration - start), 1.4)
            frame = make_story_frame(image, base_frame)
            clips.append(build_animated_image_clip(frame, duration, start, index))

        if clips and clips[0].start > 0:
            clips.insert(0, ImageClip(np.array(base_frame)).set_duration(clips[0].start))
    else:
        current_time = 0.0
        index = 0
        while current_time < total_duration:
            image = images[index % len(images)]
            duration = min(IMAGE_DURATION, total_duration - current_time)
            frame = make_story_frame(image, base_frame)
            clips.append(build_animated_image_clip(frame, duration, current_time, index))
            current_time += duration
            index += 1

    return CompositeVideoClip(clips, size=VIDEO_SIZE).set_duration(total_duration)


def draw_watermark(draw: ImageDraw.ImageDraw) -> None:
    font = load_font(WATERMARK_FONTSIZE)
    bbox = draw.textbbox((0, 0), WATERMARK_TEXT, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = VIDEO_SIZE[0] - width - WATERMARK_PADDING
    y = VIDEO_SIZE[1] - height - WATERMARK_PADDING
    draw_text_with_shadow(draw, (x, y), WATERMARK_TEXT, font=font, fill=(*TEXT_MUTED, 150))


def make_title_clip(topic: str, duration: float) -> ImageClip:
    image = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    label_font = load_font(LABEL_FONTSIZE)
    title_font = load_font(TITLE_FONTSIZE)
    subtitle_font = load_font(20)

    rounded_rectangle(draw, (84, 86, 264, 130), radius=18, fill=(*ACCENT_RED, 220))
    draw_text_with_shadow(draw, (174, 108), "CASE FILE", font=label_font, fill=(255, 255, 255, 255), anchor="mm")
    draw.rectangle((84, 162, VIDEO_SIZE[0] - 84, 166), fill=(*ACCENT_RED, 255))
    draw_text_with_shadow(draw, (VIDEO_SIZE[0] // 2, 270), topic.upper(), font=title_font, fill=(*TEXT_WHITE, 255), anchor="mm")
    draw_text_with_shadow(
        draw,
        (VIDEO_SIZE[0] // 2, 330),
        "VISUAL CASE BREAKDOWN",
        font=subtitle_font,
        fill=(*TEXT_MUTED, 255),
        anchor="mm",
        shadow_fill=(0, 0, 0, 120),
    )
    draw_watermark(draw)

    return (
        ImageClip(np.array(image))
        .set_duration(duration)
        .set_position(lambda t: (0, 10 - (18 * min(t / max(duration, 0.1), 1.0))))
        .fadein(0.35)
        .fadeout(0.25)
    )


def make_prologue_clip(topic: str, duration: float) -> ImageClip:
    image = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    kicker_font = load_font(20)
    title_font = load_font(44)
    body_font = load_font(26)

    rounded_rectangle(draw, (110, 170, VIDEO_SIZE[0] - 110, 470), radius=32, fill=(10, 10, 14, 210))
    draw.rectangle((138, 198, 332, 202), fill=(*ACCENT_RED, 255))
    draw_text_with_shadow(draw, (138, 176), "CASE PROLOGUE", font=kicker_font, fill=(*TEXT_MUTED, 255))
    draw_text_with_shadow(draw, (140, 248), topic.upper(), font=title_font, fill=(*TEXT_WHITE, 255))
    draw.multiline_text(
        (140, 314),
        "A real story shaped by obsession,\ndeception, violence, and one unforgettable detail.",
        font=body_font,
        fill=(*TEXT_WHITE, 230),
        spacing=12,
    )
    draw_text_with_shadow(
        draw,
        (140, 418),
        "Stay until the end.",
        font=body_font,
        fill=(*ACCENT_RED, 255),
    )
    draw_watermark(draw)

    return (
        ImageClip(np.array(image))
        .set_start(TITLE_DURATION)
        .set_duration(duration)
        .fadein(0.20)
        .fadeout(0.25)
    )


def group_words_into_subtitles(word_boundaries: list[dict], words_per_subtitle: int) -> list[dict]:
    subtitles = []
    for index in range(0, len(word_boundaries), words_per_subtitle):
        chunk = word_boundaries[index:index + words_per_subtitle]
        text = " ".join(word["word"] for word in chunk)
        start = chunk[0]["start"]
        end = chunk[-1]["start"] + chunk[-1]["duration"]
        subtitles.append({"text": text, "start": start, "end": end})
    return subtitles


def _draw_subtitle_stroke(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font, stroke: int = 3) -> None:
    offsets = [(-stroke, 0), (stroke, 0), (0, -stroke), (0, stroke),
               (-stroke, -stroke), (stroke, -stroke), (-stroke, stroke), (stroke, stroke)]
    for dx, dy in offsets:
        draw.multiline_text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, 200), spacing=8, align="center")
    draw.multiline_text((x, y), text, font=font, fill=(*TEXT_WHITE, 255), spacing=8, align="center")


def make_subtitle_clip(text: str, start: float, end: float) -> ImageClip:
    duration = max(end - start, 0.12)
    font = load_font(SUBTITLE_FONTSIZE)
    image = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    words = text.upper().split()
    lines: list[str] = []
    current = ""
    max_width = VIDEO_SIZE[0] - 220

    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    full_text = "\n".join(lines)
    bbox = draw.multiline_textbbox((0, 0), full_text, font=font, spacing=8)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (VIDEO_SIZE[0] - text_width) // 2
    y = VIDEO_SIZE[1] - text_height - 98
    _draw_subtitle_stroke(draw, x, y, full_text, font)
    draw_watermark(draw)

    return (
        ImageClip(np.array(image))
        .set_start(NARRATION_OFFSET + start)
        .set_end(NARRATION_OFFSET + end)
        .fadein(0.06)
        .fadeout(0.08)
    )


def draw_bell_icon(draw: ImageDraw.ImageDraw, x: int, y: int, size: int) -> None:
    bell_color = (*TEXT_WHITE, 255)
    stroke = 3
    draw.arc((x, y, x + size, y + size), start=200, end=340, fill=bell_color, width=stroke)
    draw.line((x + size * 0.28, y + size * 0.60, x + size * 0.20, y + size * 0.82), fill=bell_color, width=stroke)
    draw.line((x + size * 0.72, y + size * 0.60, x + size * 0.80, y + size * 0.82), fill=bell_color, width=stroke)
    draw.line((x + size * 0.20, y + size * 0.82, x + size * 0.80, y + size * 0.82), fill=bell_color, width=stroke)
    draw.ellipse((x + size * 0.42, y + size * 0.82, x + size * 0.58, y + size * 0.98), fill=bell_color)
    draw.arc((x - 6, y + 2, x + size * 0.30, y + size * 0.46), start=280, end=20, fill=(255, 255, 255, 120), width=2)
    draw.arc((x + size * 0.70, y + 2, x + size + 6, y + size * 0.46), start=160, end=260, fill=(255, 255, 255, 120), width=2)


def make_cta_clip(text: str, subtext: str, start: float, duration: float) -> ImageClip:
    image = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    title_font = load_font(28)
    sub_font = load_font(18)

    box_width = 460
    box_height = 92
    x1 = VIDEO_SIZE[0] - box_width - 34
    y1 = 34
    x2 = x1 + box_width
    y2 = y1 + box_height

    rounded_rectangle(draw, (x1, y1, x2, y2), radius=24, fill=CTA_BG)
    rounded_rectangle(draw, (x1 + 14, y1 + 18, x1 + 178, y1 + 70), radius=18, fill=(*ACCENT_RED, 255))
    draw_text_with_shadow(draw, (x1 + 96, y1 + 44), text, font=title_font, fill=(255, 255, 255, 255), anchor="mm")
    draw_text_with_shadow(draw, (x1 + 212, y1 + 48), subtext, font=sub_font, fill=(*TEXT_MUTED, 255), anchor="lm")
    draw_bell_icon(draw, x2 - 54, y1 + 24, 24)

    return (
        ImageClip(np.array(image))
        .set_start(start)
        .set_duration(duration)
        .set_position(lambda t: (0, -8 + (8 * min(t / max(duration, 0.1), 1.0))))
        .fadein(0.20)
        .fadeout(0.20)
    )


def make_outro_clip(start: float, duration: float) -> ImageClip:
    image = Image.new("RGBA", VIDEO_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    title_font = load_font(38)
    body_font = load_font(24)
    cta_font = load_font(28)

    rounded_rectangle(draw, (150, 170, VIDEO_SIZE[0] - 150, 500), radius=36, fill=(8, 8, 12, 225))
    draw.rectangle((182, 206, VIDEO_SIZE[0] - 182, 210), fill=(*ACCENT_RED, 255))
    draw_text_with_shadow(draw, (VIDEO_SIZE[0] // 2, 260), "THIS CASE STILL HAUNTS PEOPLE", font=title_font, fill=(*TEXT_WHITE, 255), anchor="mm")
    draw.multiline_text(
        (220, 318),
        "If you want more real cases, dark mysteries, and\nhigher-quality crime breakdowns, subscribe now.",
        font=body_font,
        fill=(*TEXT_WHITE, 228),
        spacing=12,
        align="center",
    )
    rounded_rectangle(draw, (390, 414, 890, 470), radius=22, fill=(*ACCENT_RED, 255))
    draw_text_with_shadow(draw, (640, 442), "SUBSCRIBE AND TURN ON NOTIFICATIONS", font=cta_font, fill=(255, 255, 255, 255), anchor="mm")
    draw_watermark(draw)

    return (
        ImageClip(np.array(image))
        .set_start(start)
        .set_duration(duration)
        .fadein(0.30)
        .fadeout(0.35)
    )


def mix_audio(voice: AudioFileClip, music_path: Path | None, total_duration: float) -> AudioFileClip | CompositeAudioClip:
    voice = voice.volumex(1.08).audio_fadein(0.18).set_start(NARRATION_OFFSET)
    if not music_path or not music_path.is_file():
        return voice

    music = AudioFileClip(str(music_path)).volumex(MUSIC_VOLUME).audio_fadein(1.0).audio_fadeout(1.5)
    if music.duration < total_duration:
        loops = int(total_duration / music.duration) + 1
        segments = [music.subclip(0, music.duration) for _ in range(loops)]
        from moviepy.audio.AudioClip import concatenate_audioclips

        music = concatenate_audioclips(segments)
    music = music.subclip(0, total_duration)
    return CompositeAudioClip([music, voice])


def resolve_music_path() -> Path | None:
    for candidate in (BASE_DIR / "music.wav", BASE_DIR / "music.mp3"):
        if candidate.is_file():
            return candidate
    return None


def build_video(
    audio_path: Path,
    timestamps_path: Path,
    prompts_path: Path,
    output_path: Path,
    topic: str,
    music_path: Path | None = None,
) -> None:
    if not audio_path.is_file():
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    audio = AudioFileClip(str(audio_path))
    total_duration = audio.duration + NARRATION_OFFSET

    animated_clips = load_animated_clips(ANIMATED_SCENES_DIR)
    if animated_clips:
        print(f"Using {len(animated_clips)} Runway animated clips as background...")
        background = build_background_from_animated_clips(animated_clips, total_duration)
    else:
        print("Searching for related images...")
        images = fetch_images(topic)
        prompt_timeline = load_prompt_timeline(prompts_path)
        print("Building main visual...")
        background = build_background(total_duration, images, prompt_timeline)
    title_overlay = make_title_clip(topic, TITLE_DURATION)
    prologue_overlay = make_prologue_clip(topic, PROLOGUE_DURATION)

    subtitle_clips = []
    if timestamps_path.is_file():
        word_boundaries = json.loads(timestamps_path.read_text(encoding="utf-8"))
        subtitles = group_words_into_subtitles(word_boundaries, WORDS_PER_SUBTITLE)
        print(f"Synced subtitles: {len(subtitles)}")
        for subtitle in subtitles:
            subtitle_clips.append(make_subtitle_clip(subtitle["text"], subtitle["start"], subtitle["end"]))
    else:
        print("No timestamps.json found; rendering without synced subtitles.")

    final_audio = mix_audio(audio, music_path, total_duration)
    cta_clips = [
        make_cta_clip(
            "SUBSCRIBE",
            "Turn notifications on",
            start=min(NARRATION_OFFSET + CTA_START_OFFSET, max(total_duration - CTA_DURATION - 8, 0)),
            duration=CTA_DURATION,
        ),
        make_cta_clip(
            "FOLLOW THE CHANNEL",
            "More true crime files",
            start=max(total_duration - CTA_END_OFFSET, NARRATION_OFFSET + 8),
            duration=min(CTA_DURATION, max(total_duration - max(total_duration - CTA_END_OFFSET, NARRATION_OFFSET + 8), 2)),
        ),
    ]
    outro_start = max(total_duration - 8.0, NARRATION_OFFSET + 10.0)
    outro_clip = make_outro_clip(outro_start, total_duration - outro_start)
    video = CompositeVideoClip(
        [background, title_overlay, prologue_overlay] + subtitle_clips + cta_clips + [outro_clip],
        size=VIDEO_SIZE,
    ).set_audio(final_audio)

    print(f"Exporting video ({total_duration:.0f}s)...")
    video.write_videofile(
        str(output_path),
        fps=EXPORT_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        logger=None,
    )
    print(f"Video saved to: {output_path}")


def main() -> int:
    args = parse_args()
    build_video(
        audio_path=Path(args.audio),
        timestamps_path=Path(args.timestamps),
        prompts_path=Path(args.prompts),
        output_path=Path(args.output),
        topic=args.topic,
        music_path=resolve_music_path(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
