from pytubefix import YouTube
import os

def download_youtube_video(url):
    try:
        yt = YouTube(url)
        stream = yt.streams.get_highest_resolution()
        file_path = stream.download()
        video_title = yt.title
        return file_path, video_title
    except Exception as e:
        raise ValueError(f"Ошибка при загрузке YouTube видео: {e}")