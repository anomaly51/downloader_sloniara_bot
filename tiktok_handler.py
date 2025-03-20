from TikTokApi import TikTokApi
import os
import json
import re
import asyncio


async def download_tiktok_video(url):
    try:
        async with TikTokApi() as api:
            video = await api.video(url=url)
            video_data = await video.info()
            with open("tiktok_video_data.json", "w", encoding="utf-8") as json_file:
                json.dump(video_data, json_file, indent=4, ensure_ascii=False)
            print("JSON данные о видео сохранены в 'tiktok_video_data.json'")
            video_desc = video_data.get("desc", "")
            clean_desc = re.sub(r"#\S+", "", video_desc).strip()
            print(f"Извлечённое описание без хэштегов: {clean_desc}")
            video_bytes = await video.bytes()
            video_id = video_data.get("id", "unknown")
            video_filename = f"{video_id}.mp4"
            with open(video_filename, "wb") as video_file:
                video_file.write(video_bytes)
            if os.path.exists(video_filename):
                print(f"Видео успешно скачано: {video_filename}")
                return video_filename, clean_desc if clean_desc else None
            else:
                raise FileNotFoundError("TikTok видео не найдено.")
    except Exception as e:
        raise ValueError(f"Ошибка при загрузке TikTok видео: {e}")
