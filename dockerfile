# Базовый образ Python
FROM python:3.10-slim

# Установка необходимых зависимостей, включая ffmpeg
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
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование requirements.txt и установка зависимостей
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Установка Playwright и необходимых браузеров
RUN playwright install

# Копирование всех файлов приложения
COPY . /app

# Копирование .env.prod для продакшн-окружения
COPY .env.prod /app/.env

# Запуск приложения с продакшн-окружением
CMD ["python", "main.py", "--env", "prod"]
