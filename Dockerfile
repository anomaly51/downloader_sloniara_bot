FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        wget \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m pip install --upgrade pip

RUN pip install telethon python-dotenv

RUN pip install imageio-ffmpeg

RUN pip install openai yt-dlp \
    && pip check

COPY . .

RUN mkdir -p /app/content /app/downloads /app/logs

CMD ["python", "main.py", "--env", "prod"]
