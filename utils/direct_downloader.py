import asyncio
import os
import tempfile
from urllib.parse import urlparse, urlunparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
INSTAGRAM_COOKIES_PATH = os.getenv("INSTAGRAM_COOKIES_PATH", "./instagram-cookies.txt")


def is_instagram_url(url):
    host = urlparse(url).netloc.lower()
    return host == "instagram.com" or host.endswith(".instagram.com")


def normalize_instagram_url(url):
    parsed = urlparse(url)
    clean_path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme or "https", parsed.netloc, clean_path, "", "", ""))


def _ffmpeg_location():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _prepared_cookiefile():
    if not INSTAGRAM_COOKIES_PATH or not os.path.exists(INSTAGRAM_COOKIES_PATH):
        return None, None

    with open(INSTAGRAM_COOKIES_PATH, "r", encoding="utf-8") as source:
        cookie_text = source.read().lstrip()

    if not cookie_text.startswith("# Netscape HTTP Cookie File"):
        return None, None

    temp_cookie = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="instagram-cookies-",
        suffix=".txt",
        delete=False,
    )
    try:
        temp_cookie.write(cookie_text)
        temp_cookie.flush()
        return temp_cookie.name, temp_cookie
    except Exception:
        temp_cookie.close()
        try:
            os.unlink(temp_cookie.name)
        except OSError:
            pass
        raise


def _download_with_ytdlp(url):
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    ydl_opts = {
        "format": "bv*+ba/best",
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }

    ffmpeg_location = _ffmpeg_location()
    if ffmpeg_location:
        ydl_opts["ffmpeg_location"] = ffmpeg_location

    cookiefile, temp_cookie = _prepared_cookiefile()
    if cookiefile:
        ydl_opts["cookiefile"] = cookiefile

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(normalize_instagram_url(url), download=True)
            file_path = ydl.prepare_filename(info)
            requested_downloads = info.get("requested_downloads") or []
            if requested_downloads:
                file_path = requested_downloads[0].get("filepath") or file_path
    except DownloadError as exc:
        print(f"Ошибка прямого скачивания Instagram: {exc}")
        return None
    finally:
        if temp_cookie:
            temp_cookie.close()
            try:
                os.unlink(temp_cookie.name)
            except OSError:
                pass

    if not file_path or not os.path.exists(file_path):
        return None

    return {
        "type": "video",
        "file": file_path,
        "title": info.get("title") or info.get("description") or "",
    }


async def download_direct(url):
    if not is_instagram_url(url):
        return None

    return await asyncio.to_thread(_download_with_ytdlp, url)
