import asyncio
import os
from telethon import TelegramClient, events
from collections import deque
from config import API_ID, API_HASH, PHONE_NUMBER
from utils import update_readers, handle_video_link

os.makedirs("./content", exist_ok=True)  # Создаем каталог ./content

client = TelegramClient("user", API_ID, API_HASH)
LAST_MESSAGES = deque(maxlen=5)


@client.on(events.NewMessage(pattern=r"http[s]?://[^\s]+"))
async def handler(event):
    await handle_video_link(event, client, LAST_MESSAGES)


async def main():
    print("Клиент запускается1")
    asyncio.create_task(update_readers(client, LAST_MESSAGES))
    print("Клиент запускается")
    await client.start(phone=PHONE_NUMBER)
    print("Клиент запущен. Ожидаю сообщения...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    print("Клиент запускается2")
    asyncio.run(main())

