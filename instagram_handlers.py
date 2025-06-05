import subprocess
import glob
import os
import re
import shutil
import tempfile
import json


def download_instagram_photos_with_audio(url):
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
                    title = data.get("caption", "No title found")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Error reading metadata: {e}")

        photos = []
        audio = None
        for file in glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True):
            if os.path.isfile(file):
                if file.endswith((".jpg", ".jpeg", ".png")):
                    dest_file = os.path.join(DOWNLOAD_DIR, os.path.basename(file))
                    shutil.move(file, dest_file)
                    photos.append(dest_file)
                elif file.endswith(".mp3"):
                    dest_file = os.path.join(DOWNLOAD_DIR, os.path.basename(file))
                    shutil.move(file, dest_file)
                    audio = dest_file

        return photos, audio, title


def download_instagram_video(url):
    DOWNLOAD_DIR = "./downloads"
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
        post_id = None
        title = "No title found"

        if metadata_files:
            try:
                with open(metadata_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    title = data.get("caption", "No title found")
                    post_id = data.get("id")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Error reading metadata: {e}")

        video_files = glob.glob(os.path.join(temp_dir, "**", "*.mp4"), recursive=True)
        if not video_files:
            return None, title

        source_path = video_files[0]
        if post_id:
            filename = f"{post_id}.mp4"
        else:
            filename = os.path.basename(source_path)

        dest_path = os.path.join(DOWNLOAD_DIR, filename)
        shutil.move(source_path, dest_path)

        return dest_path, title
