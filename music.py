import argparse
import math
import wave
from pathlib import Path

import numpy as np
from moviepy.editor import AudioFileClip


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT = BASE_DIR / "music.wav"
DEFAULT_VOICE_AUDIO = BASE_DIR / "audio.mp3"
INDEX_FILE = BASE_DIR / "music_indice.txt"
MUSIC_LIBRARY_DIR = BASE_DIR / "music_library"
SAMPLE_RATE = 22050

PROFILES = [
    {"name": "Dark Drone", "base_freq": 46.0, "pulse_freq": 0.14, "noise": 0.018},
    {"name": "Cinematic Pulse", "base_freq": 54.0, "pulse_freq": 0.10, "noise": 0.012},
    {"name": "Mystery Underscore", "base_freq": 63.0, "pulse_freq": 0.08, "noise": 0.010},
    {"name": "Macabre Tension", "base_freq": 39.0, "pulse_freq": 0.18, "noise": 0.022},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate background music for the short.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--voice-audio", default=str(DEFAULT_VOICE_AUDIO))
    parser.add_argument("--profile", default="", help="Force a specific music profile name.")
    return parser.parse_args()


def get_next_profile(force_name: str = "") -> dict[str, float | str]:
    if force_name:
        for profile in PROFILES:
            if str(profile["name"]).lower() == force_name.strip().lower():
                return profile
    if INDEX_FILE.is_file():
        idx = int(INDEX_FILE.read_text(encoding="utf-8").strip())
    else:
        idx = 0
    profile = PROFILES[idx % len(PROFILES)]
    INDEX_FILE.write_text(str((idx + 1) % len(PROFILES)), encoding="utf-8")
    return profile


def resolve_duration(voice_audio_path: Path) -> float:
    if voice_audio_path.is_file():
        clip = AudioFileClip(str(voice_audio_path))
        try:
            return max(clip.duration + 8.0, 75.0)
        finally:
            clip.close()
    return 90.0


def synthesize_music(duration: float, profile: dict[str, float | str]) -> np.ndarray:
    """Horror-ambient: deep sub-rumble + dissonant overtones + slow heartbeat + occasional drone swells."""
    total_samples = int(duration * SAMPLE_RATE)
    t = np.linspace(0, duration, total_samples, endpoint=False)

    base_freq = float(profile["base_freq"])
    noise_level = float(profile["noise"])
    rng = np.random.default_rng(42)

    # 1. Sub-bass rumble — felt more than heard
    sub_rumble = 0.55 * np.sin(2 * math.pi * (base_freq / 2.5) * t)
    sub_rumble += 0.35 * np.sin(2 * math.pi * (base_freq / 3.5) * t + 1.1)

    # 2. Main drone with slow detune wobble (creates unease)
    wobble = 1.0 + 0.003 * np.sin(2 * math.pi * 0.07 * t)
    drone = 0.40 * np.sin(2 * math.pi * base_freq * t * wobble)

    # 3. Dissonant minor-second overtone (the "horror interval")
    dissonance = 0.18 * np.sin(2 * math.pi * (base_freq * 1.059463) * t + 0.7)
    dissonance += 0.12 * np.sin(2 * math.pi * (base_freq * 1.414) * t + 2.3)  # tritone

    # 4. Slow heartbeat pulse (around 50 bpm = 0.83 Hz)
    heartbeat_phase = 2 * math.pi * 0.83 * t
    heartbeat_env = np.exp(-8 * (np.sin(heartbeat_phase / 2) ** 2 - 0.85).clip(min=0))
    heartbeat = 0.28 * np.sin(2 * math.pi * 38.0 * t) * heartbeat_env

    # 5. Tension swells every ~12s
    swell_freq = 1.0 / 12.0
    swell = 0.5 * (1 + np.sin(2 * math.pi * swell_freq * t - math.pi / 2))
    swell = swell ** 2  # exaggerate peaks

    # 6. Distant whisper-like high noise gated by swells
    high_noise = rng.normal(0, 1, total_samples)
    # Cheap one-pole highpass via diff
    high_noise = np.diff(high_noise, prepend=high_noise[0])
    whisper = 0.04 * high_noise * swell

    # 7. Broadband noise floor
    bed_noise = rng.normal(0.0, noise_level * 1.4, total_samples)

    # Mix
    signal = (sub_rumble + drone + dissonance + heartbeat + whisper + bed_noise)
    signal = signal * (0.55 + 0.25 * swell)  # overall envelope

    # Soft clip for analog warmth
    signal = np.tanh(signal * 1.15) * 0.92
    signal = np.clip(signal, -1.0, 1.0)

    # Stereo width with phase offset
    left = signal * 0.95
    right = np.roll(signal, 12) * 0.95
    stereo = np.column_stack([left, right])
    pcm = np.int16(stereo * 32767)
    return pcm


def write_wav(output_path: Path, pcm: np.ndarray) -> None:
    with wave.open(str(output_path), "wb") as wav_file:
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(pcm.tobytes())


def pick_library_track() -> Path | None:
    if not MUSIC_LIBRARY_DIR.is_dir():
        return None
    tracks = [
        p for p in MUSIC_LIBRARY_DIR.iterdir()
        if p.suffix.lower() in {".mp3", ".wav", ".ogg", ".flac"}
    ]
    if not tracks:
        return None
    import random
    return random.choice(tracks)


def build_music(
    output_path: Path = DEFAULT_OUTPUT,
    voice_audio_path: Path = DEFAULT_VOICE_AUDIO,
    profile_name: str = "",
) -> Path:
    library_track = pick_library_track()
    if library_track:
        import shutil
        print(f"Musica desde libreria: {library_track.name}")
        if library_track.suffix.lower() == ".wav":
            shutil.copy2(library_track, output_path)
        else:
            from moviepy.editor import AudioFileClip as _AC
            _AC(str(library_track)).write_audiofile(str(output_path.with_suffix(".wav")), logger=None)
            shutil.move(str(output_path.with_suffix(".wav")), str(output_path))
        print(f"Musica guardada en: {output_path}")
        return output_path

    profile = get_next_profile(profile_name)
    duration = resolve_duration(voice_audio_path)
    print(f"Generando musica sintetica: {profile['name']} ({duration:.0f}s)...")
    pcm = synthesize_music(duration, profile)
    write_wav(output_path, pcm)
    print(f"Musica guardada en: {output_path}")
    return output_path


if __name__ == "__main__":
    args = parse_args()
    build_music(
        output_path=Path(args.output),
        voice_audio_path=Path(args.voice_audio),
        profile_name=args.profile,
    )
