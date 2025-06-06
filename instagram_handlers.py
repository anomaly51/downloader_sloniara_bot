import subprocess
import glob
import os
import re
import shutil
import tempfile
import json


def download_instagram_content(url):
    DOWNLOAD_DIR = "./downloads"
    post_id = re.search(r"/(p|reel)/([A-Za-z0-9_-]+)", url)
    if not post_id:
        raise ValueError("Invalid Instagram URL")
    post_id = post_id.group(2)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(
            [
                "gallery-dl",
                "--cookies",
                "instagram-cookies.txt",
                "--dest",
                temp_dir,
                "--write-metadata",
                url,
            ],
            check=True,
        )
        metadata_files = glob.glob(
            os.path.join(temp_dir, "**", "*.json"), recursive=True
        )
        title = "No title found"
        if metadata_files:
            try:
                with open(metadata_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    print(data)
                    title = data.get("description") or data.get(
                        "edge_media_to_caption", {}
                    ).get("edges", [{}])[0].get("node", {}).get(
                        "text", "No title found"
                    )
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Error reading metadata: {e}")

        media_files = glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True)
        media_files = [
            f for f in media_files if f.endswith((".jpg", ".jpeg", ".png", ".mp4"))
        ]

        # Сортировка файлов по числовой части в имени для сохранения порядка
        def get_number(filename):
            match = re.search(r"_(\d+)\.", os.path.basename(filename))
            return int(match.group(1)) if match else 0

        media_files.sort(key=get_number)

        media = []
        for file in media_files:
            if file.endswith((".jpg", ".jpeg", ".png")):
                type_ = "photo"
            elif file.endswith(".mp4"):
                type_ = "video"
            else:
                continue
            dest_file = os.path.join(DOWNLOAD_DIR, os.path.basename(file))
            shutil.move(file, dest_file)
            media.append({"type": type_, "file_path": dest_file})

        audio_files = glob.glob(os.path.join(temp_dir, "**", "*.mp3"), recursive=True)
        audio = None
        if audio_files:
            audio = os.path.join(DOWNLOAD_DIR, os.path.basename(audio_files[0]))
            shutil.move(audio_files[0], audio)

        return {"media": media, "audio": audio, "title": title}


if __name__ == "__main__":
    mixed_url = "https://www.instagram.com/p/DI0AO2vo_CVgqiOnHW0E-Lc18EtQ9RZ-zd7oHI0/"
    content = download_instagram_content(mixed_url)
    print("Media:", content["media"])
    print("Audio:", content["audio"])
    print("Title:", content["title"])

