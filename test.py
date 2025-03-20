from yt_dlp import YoutubeDL

# Ссылка на ваше видео
url = "https://www.tiktok.com/@.povhistory/video/7483182895247396118?is_from_webapp=1&sender_device=pc"

# Опции (имя файла)
ydl_opts = {"outtmpl": "tiktok_video.mp4"}

# Скачивание
with YoutubeDL(ydl_opts) as ydl:
    ydl.download([url])

