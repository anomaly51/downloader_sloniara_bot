from TikTokApi import TikTokApi
import os
import json
import re
import requests


def download_tiktok_video(url):
    try:
        # Инициализация TikTok API с вашими Client Key и Client Secret
        # Замените 'your_client_key' и 'your_client_secret' на ваши реальные ключи
        api = TikTokApi(
            client_key="your_client_key", client_secret="your_client_secret"
        )

        # Извлечение ID видео из URL
        video_id = url.split("/")[-1].split("?")[0]
        print(f"Извлеченный ID видео: {video_id}")

        # Получение данных видео через TikTok API
        video_data = api.get_video_by_id(video_id)

        # Сохранение метаданных видео в JSON
        json_path = os.path.join("./content", "tiktok_video_data.json")
        os.makedirs("./content", exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as json_file:
            json.dump(video_data, json_file, indent=4, ensure_ascii=False)
        print(f"Метаданные видео сохранены в: {json_path}")

        # Извлечение описания и удаление хэштегов
        video_desc = video_data.get("desc", "")
        clean_desc = re.sub(r"#\S+", "", video_desc).strip()
        print(f"Очищенное описание: {clean_desc}")

        # Получение URL для скачивания видео
        video_url = video_data["video"]["downloadAddr"]
        print(f"URL для скачивания видео: {video_url}")

        # Скачивание видео
        video_response = requests.get(video_url)
        video_response.raise_for_status()
        video_path = os.path.join("./content", "tiktok_video.mp4")
        with open(video_path, "wb") as video_file:
            video_file.write(video_response.content)
        print(f"Видео скачано в: {video_path}")

        return video_path, clean_desc if clean_desc else None, json_path

    except Exception as e:
        raise ValueError(f"Ошибка при скачивании видео TikTok: {e}")

