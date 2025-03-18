import pyktok as pyk
import os
import json
import re


def download_tiktok_video(url):
    try:
        video_data = pyk.alt_get_tiktok_json(url)
        with open(
            os.path.join("./content", "tiktok_video_data.json"), "w", encoding="utf-8"
        ) as json_file:
            json.dump(video_data, json_file, indent=4, ensure_ascii=False)
        print("JSON данные о видео сохранены в './content/tiktok_video_data.json'")
        video_desc = (
            video_data.get("__DEFAULT_SCOPE__", {})
            .get("webapp.video-detail", {})
            .get("shareMeta", {})
            .get("desc", "")
        )
        clean_desc = re.sub(r"#\S+", "", video_desc).strip()
        print(f"Извлечённое описание без хэштегов: {clean_desc}")
        pyk.save_tiktok(url, True)
        files_in_dir = os.listdir(".")
        for file in files_in_dir:
            if file.endswith(".mp4"):
                original_path = file
                target_path = os.path.join("./content", file)
                os.rename(original_path, target_path)
                return target_path, clean_desc if clean_desc else None, target_path
        raise FileNotFoundError("TikTok видео не найдено.")
    except Exception as e:
        raise ValueError(f"Ошибка при загрузке TikTok видео: {e}")

