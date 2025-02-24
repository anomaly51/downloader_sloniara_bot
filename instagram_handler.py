import instaloader
import os

def download_instagram_video(url):
    try:
        video_title = "Instagram Video"
        loader = instaloader.Instaloader()
        post = instaloader.Post.from_shortcode(loader.context, url.split("/")[-2])
        loader.download_post(post, target="instagram_download")
        files_in_dir = os.listdir('./instagram_download')
        for file in files_in_dir:
            if file.endswith('.mp4'):
                file_path = os.path.join('./instagram_download', file)
                return file_path, video_title
        raise FileNotFoundError("Instagram видео не найдено.")
    except Exception as e:
        raise ValueError(f"Ошибка при загрузке Instagram видео: {e}")