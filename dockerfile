# Базовый образ Python
FROM python:3.10-slim

# Установка необходимых зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    curl \
    unzip \
    chromium \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libgbm1 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libasound2 \
    libxshmfence1 \
    fonts-liberation \
    libjpeg62-turbo \
    xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Установка Instaloader и других библиотек
RUN pip install --no-cache-dir telethon pytubefix pyktok instaloader playwright

# Установка Playwright и необходимых браузеров
RUN playwright install

# Создание рабочей директории
WORKDIR /app

# Копирование всех файлов приложения
COPY . /app

# Запуск приложения
CMD ["python", "main.py"]