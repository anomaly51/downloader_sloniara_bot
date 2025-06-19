import asyncio
import os
from telethon import TelegramClient, events
from collections import deque
from dotenv import load_dotenv
import argparse

parser = argparse.ArgumentParser(description="Telegram бот для скачивания видео")
parser.add_argument("--env", default="dev", help="Окружение: prod или dev")
args = parser.parse_args()

load_dotenv(f".env.{args.env}")

SESSION_NAME = os.getenv("SESSION_NAME")
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
PHONE_NUMBER = os.getenv("PHONE_NUMBER")

if not all([SESSION_NAME, API_ID, API_HASH, PHONE_NUMBER]):
    print(
        f"Ошибка: Не все переменные окружения установлены. Проверьте файл .env.{args.env}"
    )
    exit(1)

API_ID = int(API_ID)

os.makedirs("./content", exist_ok=True)

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

LAST_MESSAGES = deque(maxlen=5)


@client.on(events.NewMessage(pattern=r"http[s]?://[^\s]+"))
async def handler(event):
    from utils.content_sender import handle_content_link

    await handle_content_link(event, client, LAST_MESSAGES)


async def main():
    print(f"Клиент запускается с сессией: {SESSION_NAME}.session")
    from utils.message_readers import update_readers

    asyncio.create_task(update_readers(client, LAST_MESSAGES))
    await client.start(phone=PHONE_NUMBER)
    print("Клиент запущен. Ожидаю сообщения...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())

