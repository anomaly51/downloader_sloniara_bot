import pyktok as pyk
import os
import json
import re

def download_tiktok_video(url):
    try:
        # Получаем JSON данных о видео
        video_data = pyk.alt_get_tiktok_json(url)
        
        # Сохраняем JSON в файл для отладки
        with open("tiktok_video_data.json", "w", encoding="utf-8") as json_file:
            json.dump(video_data, json_file, indent=4, ensure_ascii=False)
        print("JSON данные о видео сохранены в 'tiktok_video_data.json'")
        
        # Попробуем извлечь описание видео из __DEFAULT_SCOPE__["webapp.video-detail"]["shareMeta"]["desc"]
        video_desc = (
            video_data.get("__DEFAULT_SCOPE__", {})
            .get("webapp.video-detail", {})
            .get("shareMeta", {})
            .get("desc", "")
        )
        
        # Удаляем хэштеги из описания
        clean_desc = re.sub(r"#\S+", "", video_desc).strip()
        print(f"Извлечённое описание без хэштегов: {clean_desc}")
        
        # Скачиваем видео
        pyk.save_tiktok(url, True)
        
        # Ищем скачанный файл .mp4
        files_in_dir = os.listdir('.')
        for file in files_in_dir:
            if file.endswith('.mp4'):
                file_path = os.path.join('.', file)
                print(f"Видео успешно скачано: {file_path}")
                return file_path, clean_desc if clean_desc else None

        raise FileNotFoundError("TikTok видео не найдено.")
    except Exception as e:
        raise ValueError(f"Ошибка при загрузке TikTok видео: {e}")