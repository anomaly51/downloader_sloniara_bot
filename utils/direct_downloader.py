import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from PIL import Image, ImageOps

DOWNLOAD_DIR = Path(os.getenv("DOWNLOAD_DIR", "./downloads"))
INSTAGRAM_COOKIES_PATH = os.getenv("INSTAGRAM_COOKIES_PATH", "./instagram-cookies.txt")
TIKTOK_COOKIES_PATH = os.getenv("TIKTOK_COOKIES_PATH", "./tiktok-cookies.txt")
GALLERY_DL_TIMEOUT = int(os.getenv("GALLERY_DL_TIMEOUT", "240"))

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav"}


def _host_matches(url, domain):
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    return host == domain or host.endswith(f".{domain}")


def is_instagram_url(url):
    return _host_matches(url, "instagram.com")


def is_tiktok_url(url):
    return _host_matches(url, "tiktok.com")


def is_gallery_dl_url(url):
    return is_instagram_url(url) or is_tiktok_url(url)


def normalize_instagram_url(url):
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme or "https", parsed.netloc, clean_path, "", "", ""))


def _normalized_url(url):
    return normalize_instagram_url(url) if is_instagram_url(url) else url


def _cookie_path(url):
    if is_instagram_url(url):
        return INSTAGRAM_COOKIES_PATH
    if is_tiktok_url(url):
        return TIKTOK_COOKIES_PATH
    return None


def _ffmpeg_executable():
    return os.getenv("FFMPEG_BINARY") or shutil.which("ffmpeg") or "ffmpeg"


def _ffprobe_executable():
    return os.getenv("FFPROBE_BINARY") or shutil.which("ffprobe") or "ffprobe"


def _run(command, *, timeout=GALLERY_DL_TIMEOUT):
    return subprocess.run(
        command,
        check=True,
        text=True,
        capture_output=True,
        timeout=timeout,
    )


def _load_metadata(path):
    try:
        with path.open("r", encoding="utf-8") as metadata_file:
            return json.load(metadata_file)
    except (OSError, json.JSONDecodeError):
        return {}


def _classify_assets(workdir):
    assets = {"photos": [], "videos": [], "audio": [], "metadata": []}
    described_paths = set()

    for metadata_path in sorted(workdir.glob("*.json")):
        media_path = metadata_path.with_suffix("")
        if not media_path.is_file():
            continue

        metadata = _load_metadata(metadata_path)
        assets["metadata"].append(metadata)
        described_paths.add(media_path.resolve())
        suffix = media_path.suffix.lower()

        if metadata.get("audio_url") or suffix in AUDIO_EXTENSIONS:
            assets["audio"].append(media_path)
        elif suffix in IMAGE_EXTENSIONS:
            assets["photos"].append(media_path)
        elif suffix in VIDEO_EXTENSIONS:
            assets["videos"].append(media_path)

    for media_path in sorted(workdir.iterdir()):
        if not media_path.is_file() or media_path.resolve() in described_paths:
            continue
        suffix = media_path.suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            assets["photos"].append(media_path)
        elif suffix in AUDIO_EXTENSIONS:
            assets["audio"].append(media_path)
        elif suffix in VIDEO_EXTENSIONS:
            assets["videos"].append(media_path)

    return assets


def _content_title(metadata_items):
    for metadata in metadata_items:
        description = (metadata.get("description") or "").strip()
        if description:
            return description

    for metadata in metadata_items:
        audio_title = (metadata.get("audio_title") or "").strip()
        audio_artist = (metadata.get("audio_artist") or "").strip()
        if audio_title and audio_artist:
            return f"{audio_title} — {audio_artist}"
        if audio_title:
            return audio_title

    return ""


def _audio_duration(audio_path):
    result = _run(
        [
            _ffprobe_executable(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        timeout=30,
    )
    return float(result.stdout.strip())


def _canvas_size(photo_path):
    with Image.open(photo_path) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size

    scale = min(1080 / width, 1920 / height, 1.0)
    width = max(2, int(width * scale) // 2 * 2)
    height = max(2, int(height * scale) // 2 * 2)
    return width, height


def _normalize_photo(source, destination, canvas_size):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        fitted = ImageOps.contain(image, canvas_size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", canvas_size, "black")
        offset = (
            (canvas_size[0] - fitted.width) // 2,
            (canvas_size[1] - fitted.height) // 2,
        )
        canvas.paste(fitted, offset)
        canvas.save(destination, format="JPEG", quality=92, optimize=True)


def compose_photo_slideshow(photos, audio_path, output_path):
    """Build a Telegram-compatible MP4 covering the complete audio track."""
    if not photos or not audio_path:
        return None

    duration = _audio_duration(audio_path)
    if duration <= 0:
        return None

    output_path = Path(output_path)
    slideshow_dir = output_path.parent / "slideshow"
    slideshow_dir.mkdir(parents=True, exist_ok=True)
    canvas_size = _canvas_size(photos[0])
    normalized = []

    for index, photo in enumerate(photos):
        normalized_path = slideshow_dir / f"{index:04d}.jpg"
        _normalize_photo(photo, normalized_path, canvas_size)
        normalized.append(normalized_path)

    if len(normalized) == 1:
        video_input = ["-loop", "1", "-i", str(normalized[0])]
    else:
        seconds_per_photo = duration / len(normalized)
        manifest_path = slideshow_dir / "manifest.txt"
        with manifest_path.open("w", encoding="utf-8") as manifest:
            for image_path in normalized:
                manifest.write(f"file '{image_path.as_posix()}'\n")
                manifest.write(f"duration {seconds_per_photo:.6f}\n")
            manifest.write(f"file '{normalized[-1].as_posix()}'\n")
        video_input = ["-f", "concat", "-safe", "0", "-i", str(manifest_path)]

    _run(
        [
            _ffmpeg_executable(),
            "-y",
            *video_input,
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{duration:.6f}",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-shortest",
            str(output_path),
        ]
    )
    return str(output_path) if output_path.is_file() else None


def _build_content(assets, workdir):
    photos = assets["photos"]
    videos = assets["videos"]
    audio = assets["audio"]
    title = _content_title(assets["metadata"])
    base = {"title": title, "_workdir": str(workdir)}

    if photos and audio:
        try:
            slideshow = compose_photo_slideshow(
                photos, audio[0], workdir / "photo-audio.mp4"
            )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            print(f"Не удалось собрать photo+audio видео: {exc}")
            slideshow = None

        if slideshow:
            return {**base, "type": "video", "file": slideshow}

        return {
            **base,
            "type": "photos",
            "files": [str(path) for path in photos],
            "audio": str(audio[0]),
        }

    if len(videos) == 1 and not photos:
        return {**base, "type": "video", "file": str(videos[0])}

    if photos and not videos:
        return {**base, "type": "photos", "files": [str(path) for path in photos]}

    if videos or photos:
        media = [
            *({"type": "photo", "file_path": str(path)} for path in photos),
            *({"type": "video", "file_path": str(path)} for path in videos),
        ]
        return {**base, "type": "mixed", "media": media}

    if audio:
        return {**base, "type": "audio", "file": str(audio[0])}

    return None


def _download_with_gallery_dl(url):
    if not is_gallery_dl_url(url):
        return None

    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="gallery-dl-", dir=DOWNLOAD_DIR))
    command = [
        sys.executable,
        "-m",
        "gallery_dl",
        "-D",
        str(workdir),
        "--write-metadata",
        "-o",
        "extractor.instagram.audio=true",
        "-o",
        "extractor.tiktok.audio=true",
    ]

    cookie_path = _cookie_path(url)
    if cookie_path and os.path.isfile(cookie_path):
        command.extend(["-C", cookie_path])
    command.append(_normalized_url(url))

    try:
        result = _run(command)
        if result.stdout.strip():
            print(result.stdout.strip())
        assets = _classify_assets(workdir)
        content = _build_content(assets, workdir)
        if content:
            return content
        print("gallery-dl не вернул поддерживаемых медиафайлов")
    except subprocess.TimeoutExpired:
        print(f"gallery-dl превысил таймаут {GALLERY_DL_TIMEOUT} секунд")
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or str(exc)).strip()
        print(f"Ошибка gallery-dl: {details}")
    except Exception as exc:
        print(f"Неожиданная ошибка gallery-dl: {exc}")

    shutil.rmtree(workdir, ignore_errors=True)
    return None


async def download_direct(url):
    if not is_gallery_dl_url(url):
        return None
    return await asyncio.to_thread(_download_with_gallery_dl, url)
