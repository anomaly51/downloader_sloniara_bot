import asyncio
import os
from telethon import TelegramClient, events
from collections import deque
from dotenv import load_dotenv
import argparse

# Парсим аргумент командной строки для выбора окружения
parser = argparse.ArgumentParser(description="Telegram бот для скачивания видео")
parser.add_argument("--env", default="dev", help="Окружение: prod или dev")
args = parser.parse_args()

# Загружаем переменные окружения из соответствующего файла .env
load_dotenv(f".env.{args.env}")

# Получаем учетные данные из переменных окружения
SESSION_NAME = os.getenv("SESSION_NAME")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")

# Проверяем, что все переменные установлены
if not all([SESSION_NAME, API_ID, API_HASH, PHONE_NUMBER]):
    print("Ошибка: Не все переменные окружения установлены. Проверь файл .env")
    exit(1)

# Преобразуем API_ID в int, так как Telethon требует целое число
API_ID = int(API_ID)

# Создаем папку для контента
os.makedirs("./content", exist_ok=True)

# Инициализируем клиент Telegram с именем сессии из SESSION_NAME
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

LAST_MESSAGES = deque(maxlen=5)


@client.on(events.NewMessage(pattern=r"http[s]?://[^\s]+"))
async def handler(event):
    from utils import (
        handle_content_link,
    )  # Импорт здесь, чтобы избежать циклического импорта

    await handle_content_link(event, client, LAST_MESSAGES)


async def main():
    print(f"Клиент запускается с сессией: {SESSION_NAME}.session")
    from utils import (
        update_readers,
    )  # Импорт здесь, чтобы избежать циклического импорта

    asyncio.create_task(update_readers(client, LAST_MESSAGES))
    await client.start(phone=PHONE_NUMBER)
    print("Клиент запущен. Ожидаю сообщения...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

