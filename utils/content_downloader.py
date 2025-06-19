from .content_converters import (
    convert_video_to_mp3,
    convert_video_to_ogg_opus,
    get_conversion_action,
)
from instagram_handlers import download_instagram_content
from tiktok_handlers import download_tiktok_video, download_tiktok_photos_with_audio
from youtube_handler import download_youtube_video


async def download_tiktok(resolved_url, instruction):
    """Обрабатывает контент с TikTok."""
    if "/photo/" in resolved_url:
        photos_filename, audio_filename, video_title = (
            download_tiktok_photos_with_audio(resolved_url)
        )
        if not photos_filename:
            return None
        return {
            "type": "photos",
            "files": photos_filename,
            "audio": audio_filename,
            "title": video_title,
        }
    else:
        file_path, video_title = download_tiktok_video(resolved_url)
        if instruction:
            action = await get_conversion_action(instruction)
            if action == "mp3":
                output_path = convert_video_to_mp3(file_path)
                return {"type": "audio", "file": output_path, "title": video_title}
            elif action == "voice":
                output_path = convert_video_to_ogg_opus(file_path)
                return {"type": "voice", "file": output_path}
        return {"type": "video", "file": file_path, "title": video_title}


async def download_youtube(resolved_url, instruction):
    """Обрабатывает контент с YouTube."""
    file_path, video_title = download_youtube_video(resolved_url)
    if instruction:
        action = await get_conversion_action(instruction)
        if action == "mp3":
            output_path = convert_video_to_mp3(file_path)
            return {"type": "audio", "file": output_path, "title": video_title}
        elif action == "voice":
            output_path = convert_video_to_ogg_opus(file_path)
            return {"type": "voice", "file": output_path}
    return {"type": "video", "file": file_path, "title": video_title}


async def download_instagram(resolved_url, instruction):
    """Обрабатывает контент с Instagram."""
    content = download_instagram_content(resolved_url)
    media = content["media"]
    audio = content["audio"]
    video_title = content["title"]
    if not media:
        return None
    return {"type": "mixed", "media": media, "audio": audio, "title": video_title}
