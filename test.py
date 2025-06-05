import subprocess
import json

URL = "https://www.tiktok.com/@storymur/video/7468695039820975382"
COOKIES_FILE = "tiktok-cookies.txt"

info = subprocess.run(
    ["yt-dlp", "--dump-json", URL, "--cookies", COOKIES_FILE],
    capture_output=True,
    text=True,
)
print("Title:", json.loads(info.stdout)["title"])
subprocess.run(["yt-dlp", URL, "--cookies", COOKIES_FILE])

