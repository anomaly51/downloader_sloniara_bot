import subprocess
import glob
import os
import re
import shutil
import tempfile
import json


def download_tiktok_photos_with_audio(url):
    DOWNLOAD_DIR = "./downloads"
    video_id = re.search(r"/photo/(\d+)", url).group(1)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(
            [
                "gallery-dl",
                "--cookies",
                "tiktok-cookies.txt",
                "--dest",
                temp_dir,
                "--write-metadata",
                "--filename",
                f"{video_id}_{{num:02d}}.{{extension}}",
                url,
            ]
        )
        metadata_files = glob.glob(os.path.join(temp_dir, "*.json"))
        title = "No title found"
        if metadata_files:
            with open(metadata_files[0], "r") as f:
                data = json.load(f)
                title = data.get("desc", "No title found")
        for file in glob.glob(os.path.join(temp_dir, "**", "*"), recursive=True):
            if os.path.isfile(file) and file.endswith((".jpg", ".mp3")):
                shutil.move(file, os.path.join(DOWNLOAD_DIR, os.path.basename(file)))
    photos_filename = glob.glob(os.path.join(DOWNLOAD_DIR, f"{video_id}_*.jpg"))
    audio_filename = next(iter(glob.glob(os.path.join(DOWNLOAD_DIR, "*.mp3"))), None)
    return photos_filename, audio_filename, title


def download_tiktok_video(url):
    DOWNLOAD_DIR = "./downloads"
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        subprocess.run(
            [
                "gallery-dl",
                "--cookies",
                "tiktok-cookies.txt",
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
        video_id = None
        title = "No title found"

        if metadata_files:
            try:
                with open(metadata_files[0], "r", encoding="utf-8") as f:
                    data = json.load(f)
                    title = data.get("desc", "No title found")
                    video_id = str(data.get("id"))  # Get ID from metadata
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                print(f"Error reading metadata: {e}")

        video_files = glob.glob(os.path.join(temp_dir, "**", "*.mp4"), recursive=True)
        if not video_files:
            return None, title

        # Determine final filename
        source_path = video_files[0]
        if video_id:
            filename = f"{video_id}.mp4"
        else:
            filename = os.path.basename(source_path)

        # Move to download directory
        dest_path = os.path.join(DOWNLOAD_DIR, filename)
        shutil.move(source_path, dest_path)

        return dest_path, title


if __name__ == "__main__":
    photo_url = "https://www.tiktok.com/@goroh_official0/photo/7510602525402238213?_d=secCgYIASAHKAESPgo8Wy6w4r6Or9akwlDB29H4gBWtnOZeKtb5%2FnT%2Bovs3B6iaajlOetQ3taNoWVgb4YUWwoqzS%2BOPI7RAH1tLGgA%3D&_r=1&_svg=1&aweme_type=150&checksum=e2688f32c5398bf05137e58c26ac36f4993ae7be4a2f268f85568bb7626b1ed0&cover_exp=v1&link_reflow_popup_iteration_sharer=%7B%22click_empty_to_play%22%3A1%2C%22dynamic_cover%22%3A1%2C%22follow_to_play_duration%22%3A-1.0%2C%22profile_clickable%22%3A1%7D&pic_cnt=9&preview_pb=0&sec_user_id=MS4wLjABAAAA0UNIbWMA5O1qeAB1n4lIT4J3rmjRUdz1yS-0XFIQuBJFgsPY6CYVCsuOFHRmNmou&share_app_id=1233&share_item_id=7510602525402238213&share_link_id=874b2cc8-801f-4f44-85a0-5e476676e5e6&share_scene=11&sharer_language=ru&social_share_type=14&source=h5_m&timestamp=1748905830&u_code=dja2el4a8dle15&ug_btm=b2001&ug_photo_idx=0&ugbiz_name=UNKNOWN&user_id=6978488395807032325&utm_campaign=client_share&utm_medium=android&utm_source=copy"
    video_url = "https://vm.tiktok.com/ZMBrKn5CV"
    print("Downloading photos and audio...")
    photos_filename, audio_filename, photo_title = download_tiktok_photos_with_audio(
        photo_url
    )
    print("Photos:", photos_filename)
    print("Audio:", audio_filename)
    print("Photo Title:", photo_title)
    print("\nDownloading video...")
    video_filename, title = download_tiktok_video(video_url)
    print("Video:", video_filename)
    print("Video Title:", title)
