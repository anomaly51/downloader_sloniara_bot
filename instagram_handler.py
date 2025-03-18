import instaloader
import os


def download_instagram_video(url):
    try:
        loader = instaloader.Instaloader()
        post = instaloader.Post.from_shortcode(loader.context, url.split("/")[-2])
        target_dir = os.path.join("./content", post.shortcode)
        loader.download_post(post, target=target_dir)
        for root, dirs, files in os.walk(target_dir):
            for file in files:
                if file.endswith(".mp4"):
                    file_path = os.path.join(root, file)
                    return file_path, "Instagram Video", target_dir
        raise FileNotFoundError("Instagram видео не найдено.")
    except Exception as e:
        raise ValueError(f"Ошибка при загрузке Instagram видео: {e}")

