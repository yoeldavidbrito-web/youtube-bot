import argparse
from pathlib import Path

from moviepy.editor import VideoFileClip, concatenate_videoclips


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INTRO = BASE_DIR / "creatomate_intro.mp4"
DEFAULT_MAIN = BASE_DIR / "base_video.mp4"
DEFAULT_OUTPUT = BASE_DIR / "video.mp4"
VIDEO_SIZE = (1920, 1080)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepend a Creatomate intro to the main video.")
    parser.add_argument("--intro", default=str(DEFAULT_INTRO))
    parser.add_argument("--main", default=str(DEFAULT_MAIN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def fit_intro(clip: VideoFileClip) -> VideoFileClip:
    intro = clip.resize(height=VIDEO_SIZE[1])
    return intro.on_color(size=VIDEO_SIZE, color=(6, 6, 10), pos=("center", "center"))


def main() -> int:
    args = parse_args()
    intro_path = Path(args.intro)
    main_path = Path(args.main)
    output_path = Path(args.output)

    if not intro_path.is_file():
        raise FileNotFoundError(f"Intro not found: {intro_path}")
    if not main_path.is_file():
        raise FileNotFoundError(f"Main video not found: {main_path}")

    intro_clip = VideoFileClip(str(intro_path))
    main_clip = VideoFileClip(str(main_path))

    try:
        final_clip = concatenate_videoclips([fit_intro(intro_clip), main_clip], method="compose")
        final_clip.write_videofile(
            str(output_path),
            fps=main_clip.fps or 24,
            codec="libx264",
            audio_codec="aac",
            preset="ultrafast",
            threads=4,
            remove_temp=False,
            logger=None,
        )
    finally:
        intro_clip.close()
        main_clip.close()
        try:
            final_clip.close()
        except Exception:
            pass

    print(f"Final video saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
