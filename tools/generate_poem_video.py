from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = Path(tempfile.gettempdir()) / "xuanqiong_wenshu_media_pipeline"
DEFAULT_TITLE = "静夜思"
DEFAULT_TEXT = "床前明月光\n疑是地上霜\n举头望明月\n低头思故乡"
DEFAULT_VOICE = "Microsoft Huihui Desktop"
FONT_FILE = Path(r"C:\Windows\Fonts\msyh.ttc")


def run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"命令执行失败：{' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def read_text(args: argparse.Namespace) -> str:
    if args.text:
        return args.text.strip()
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8").strip()
    return DEFAULT_TEXT


def sanitize_filename(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "sample"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_utf8(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def ffmpeg_filter_path(path: Path) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:")


def escape_drawtext_text(text: str) -> str:
    escaped = text.replace("\\", r"\\")
    escaped = escaped.replace(":", r"\:")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace("%", r"\%")
    escaped = escaped.replace(",", r"\,")
    return escaped


def synthesize_sapi(text: str, output_wav: Path, voice: str, rate: int) -> None:
    escaped_voice = voice.replace("'", "''")
    escaped_output = str(output_wav).replace("'", "''")
    ps_script = f"""$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$text = @'
{text}
'@
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
    $synth.SelectVoice('{escaped_voice}')
}} catch {{
    $voices = $synth.GetInstalledVoices() | ForEach-Object {{ $_.VoiceInfo.Name }}
    throw "Voice not found. Available voices: $($voices -join ', ')"
}}
$synth.Rate = {rate}
$synth.Volume = 100
$synth.SetOutputToWaveFile('{escaped_output}')
$synth.Speak($text)
$synth.Dispose()
"""
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write(ps_script)
        script_path = Path(handle.name)
    try:
        run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)])
    finally:
        script_path.unlink(missing_ok=True)


def audio_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ]
    )
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def build_spoken_text(title: str, raw_text: str) -> str:
    lines = [line.strip("，。！？；、,.!?; ") for line in raw_text.splitlines() if line.strip()]
    spoken = "。".join(lines)
    return f"{title}。{spoken}。"


def build_segments(raw_text: str) -> list[str]:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if lines:
        return lines
    parts = re.split(r"(?<=[。！？!?；;])", raw_text)
    return [part.strip() for part in parts if part.strip()]


def ass_timestamp(seconds: float) -> str:
    total_centis = max(int(round(seconds * 100)), 0)
    hours, rem = divmod(total_centis, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, centis = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def write_ass_subtitles(path: Path, lines: list[str], duration: float) -> None:
    text = r"\N".join(line.strip() for line in lines if line.strip())
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 720
PlayResY: 1280

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Poem,Microsoft YaHei,30,&H00FFFFFF,&H000000FF,&H00512F22,&H28000000,0,0,0,0,100,100,0,0,1,2,0,2,80,80,180,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    dialogue = (
        f"Dialogue: 0,0:00:00.60,{ass_timestamp(duration)},Poem,,0,0,0,,{text}\n"
    )
    write_utf8(path, header + dialogue)


def generate_bgm(output_wav: Path, duration: float) -> None:
    fade_start = max(duration - 2.0, 0.5)
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=196:sample_rate=44100:duration={duration:.3f},volume=0.035",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=262:sample_rate=44100:duration={duration:.3f},volume=0.025",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=392:sample_rate=44100:duration={duration:.3f},volume=0.018",
            "-filter_complex",
            (
                f"[0:a][1:a][2:a]amix=inputs=3:normalize=0,"
                f"aecho=0.8:0.7:40:0.20,afade=t=in:st=0:d=1.2,"
                f"afade=t=out:st={fade_start:.3f}:d=1.8"
            ),
            str(output_wav),
        ]
    )


def render_video(
    *,
    title: str,
    subtitles_file: Path,
    narration_wav: Path,
    bgm_wav: Path,
    duration: float,
    output_mp4: Path,
) -> None:
    bg_duration = max(duration + 0.2, 3.0)
    subtitles_filter_file = ffmpeg_filter_path(subtitles_file)
    font_filter_file = ffmpeg_filter_path(FONT_FILE)
    escaped_title = escape_drawtext_text(title)

    video_filter = (
        f"[0:v]format=yuv420p,"
        f"drawbox=x=42:y=80:w=636:h=1120:color=black@0.18:t=fill,"
        f"drawtext=fontfile='{font_filter_file}':text='{escaped_title}':"
        f"fontcolor=white:fontsize=60:x=(w-text_w)/2:y=165:shadowcolor=black@0.55:shadowx=2:shadowy=2,"
        f"subtitles='{subtitles_filter_file}',"
        f"drawtext=fontfile='{font_filter_file}':text='AI配音与本地合成样片':"
        f"fontcolor=white@0.78:fontsize=24:x=(w-text_w)/2:y=h-120:shadowcolor=black@0.4:shadowx=1:shadowy=1[vout]"
    )
    audio_filter = "[1:a]volume=1.35[voice];[2:a]volume=0.20[bgm];[voice][bgm]amix=inputs=2:duration=first:normalize=0[aout]"

    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            (
                "gradients=size=720x1280:rate=30:"
                "c0=0x102542:c1=0x355070:c2=0x8d6e63:c3=0xe7c9a9:"
                f"nb_colors=4:duration={bg_duration:.3f}:speed=0.012:type=radial"
            ),
            "-i",
            str(narration_wav),
            "-i",
            str(bgm_wav),
            "-filter_complex",
            f"{audio_filter};{video_filter}",
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(output_mp4),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成本地中文诗词/文案视频示例。")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="视频标题。")
    parser.add_argument("--text", help="原始中文文本。")
    parser.add_argument("--text-file", help="UTF-8 文本文件路径。")
    parser.add_argument("--voice", default=DEFAULT_VOICE, help="Windows SAPI 语音名称。")
    parser.add_argument("--rate", type=int, default=-1, help="Windows SAPI 语速。")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="输出根目录。")
    args = parser.parse_args()

    if not FONT_FILE.exists():
        raise FileNotFoundError(f"Font not found: {FONT_FILE}")

    title = args.title.strip() or DEFAULT_TITLE
    raw_text = read_text(args)
    spoken_text = build_spoken_text(title, raw_text)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = sanitize_filename(title)
    out_dir = ensure_dir(Path(args.output_root) / f"{timestamp}_{slug}")

    source_text_path = out_dir / "source_text.txt"
    spoken_text_path = out_dir / "spoken_text.txt"
    title_path = out_dir / "title.txt"
    display_text_path = out_dir / "display_text.txt"
    subtitles_path = out_dir / "poem.ass"
    narration_path = out_dir / "narration.wav"
    bgm_path = out_dir / "bgm.wav"
    final_video_path = out_dir / f"{slug}.mp4"
    metadata_path = out_dir / "metadata.json"

    write_utf8(source_text_path, raw_text + "\n")
    write_utf8(spoken_text_path, spoken_text + "\n")
    write_utf8(title_path, title + "\n")
    segments = build_segments(raw_text)
    write_utf8(display_text_path, "\n".join(segments) + "\n")

    synthesize_sapi(spoken_text, narration_path, args.voice, args.rate)
    narration_seconds = audio_duration(narration_path)
    write_ass_subtitles(subtitles_path, segments, narration_seconds)
    generate_bgm(bgm_path, narration_seconds)
    render_video(
        title=title,
        subtitles_file=subtitles_path,
        narration_wav=narration_path,
        bgm_wav=bgm_path,
        duration=narration_seconds,
        output_mp4=final_video_path,
    )

    metadata = {
        "title": title,
        "voice": args.voice,
        "rate": args.rate,
        "narration_seconds": round(narration_seconds, 3),
        "source_text": raw_text,
        "spoken_text": spoken_text,
        "artifacts": {
            "source_text": str(source_text_path),
            "spoken_text": str(spoken_text_path),
            "title_text": str(title_path),
            "display_text": str(display_text_path),
            "subtitles_ass": str(subtitles_path),
            "narration_wav": str(narration_path),
            "bgm_wav": str(bgm_path),
            "final_mp4": str(final_video_path),
        },
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
