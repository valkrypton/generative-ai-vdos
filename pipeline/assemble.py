"""Stage 4: FFmpeg assembly — Ken Burns over stills, burned captions, music bed."""
import json
import random
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from .schema import ShotPlan

FPS = 30


def _run(cmd: List[str], cwd: Optional[Path] = None) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd)}\n{result.stderr[-2000:]}")


def _duration(media: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(media)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def _srt_time(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _build_srt(audio_dir: Path, scene_durations: List[float], srt_path: Path) -> None:
    """Chunk edge-tts word timings into ~4-word captions with global offsets."""
    entries = []
    offset = 0.0
    for i, dur in enumerate(scene_durations):
        words = json.loads((audio_dir / f"scene_{i:02d}.words.json").read_text())
        chunk: List[dict] = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 4:
                entries.append((offset + chunk[0]["start"],
                                offset + chunk[-1]["start"] + chunk[-1]["duration"],
                                " ".join(c["text"] for c in chunk)))
                chunk = []
        if chunk:
            entries.append((offset + chunk[0]["start"],
                            offset + chunk[-1]["start"] + chunk[-1]["duration"],
                            " ".join(c["text"] for c in chunk)))
        offset += dur

    lines = []
    for n, (start, end, text) in enumerate(entries, 1):
        lines.append(f"{n}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
    srt_path.write_text("\n".join(lines))


def assemble(plan: ShotPlan, work_dir: Path, music_path: Optional[Path] = None) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found — install it with: brew install ffmpeg")

    images_dir = work_dir / "images"
    video_dir = work_dir / "video"
    audio_dir = work_dir / "audio"
    clips_dir = work_dir / "clips"
    clips_dir.mkdir(exist_ok=True)

    # Per-scene clip + that scene's voiceover. An animated clip from the
    # optional animate stage (video/scene_NN.mp4) is preferred — looped and
    # trimmed to the narration; otherwise Ken Burns over the still image.
    scene_durations = []
    clip_paths = []
    for i in range(len(plan.scenes)):
        img = images_dir / f"scene_{i:02d}.png"
        vid = video_dir / f"scene_{i:02d}.mp4"
        mp3 = audio_dir / f"scene_{i:02d}.mp3"
        clip = clips_dir / f"scene_{i:02d}.mp4"
        dur = _duration(mp3) + 0.3  # small breath between scenes
        if vid.exists():
            _run([
                "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(vid), "-i", str(mp3),
                "-filter_complex",
                f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                f"crop=1920:1080,fps={FPS}[v];[1:a]apad[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100",
                "-t", f"{dur:.3f}", str(clip),
            ])
            source = "animated"
        else:
            frames = int(dur * FPS)
            zoom_in = i % 2 == 0  # alternate zoom direction for variety
            zexpr = f"1+0.0010*on" if zoom_in else f"1.15-0.0010*on"
            _run([
                "ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-i", str(img),
                "-i", str(mp3),
                "-filter_complex",
                f"[0:v]scale=2304:1296,zoompan=z='{zexpr}':d={frames}:"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1920x1080:fps={FPS}[v];"
                f"[1:a]apad[a]",
                "-map", "[v]", "-map", "[a]",
                "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "44100",
                "-t", f"{dur:.3f}", str(clip),
            ])
            source = "ken burns"
        scene_durations.append(dur)
        clip_paths.append(clip)
        print(f"  assemble: scene clip {i + 1}/{len(plan.scenes)} ({source})")

    # Concat all scene clips.
    concat_list = work_dir / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths))
    raw = work_dir / "video_raw.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
          "-c", "copy", str(raw)])

    # Captions from edge-tts word timings.
    srt = work_dir / "captions.srt"
    _build_srt(audio_dir, scene_durations, srt)

    # Final pass: burn captions, mix music under the voiceover.
    final = work_dir / "final.mp4"
    sub_filter = (f"subtitles={srt.name}:force_style="
                  f"'FontSize=18,Bold=1,Outline=2,MarginV=40'")
    if music_path is not None:
        _run([
            "ffmpeg", "-y", "-i", str(raw.resolve()), "-stream_loop", "-1", "-i", str(music_path.resolve()),
            "-filter_complex",
            f"[0:v]{sub_filter}[v];[1:a]volume=0.12[m];"
            f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(final.resolve()),
        ], cwd=work_dir)
    else:
        _run(["ffmpeg", "-y", "-i", str(raw.resolve()), "-vf", sub_filter,
              "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
              "-c:a", "copy", str(final.resolve())], cwd=work_dir)
    return final


def pick_music(music_root: Path, mood: str) -> Optional[Path]:
    """Pick a random track from music/<mood>/ (fall back to any track)."""
    if not music_root.exists():
        return None
    mood_dir = music_root / mood
    pool = list(mood_dir.glob("*.mp3")) if mood_dir.exists() else []
    if not pool:
        pool = list(music_root.rglob("*.mp3"))
    return random.choice(pool) if pool else None
