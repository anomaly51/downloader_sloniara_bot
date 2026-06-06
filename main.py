import asyncio
import os
import re
from telethon import TelegramClient, events
from telethon.errors import AuthKeyDuplicatedError
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

READERS_TRACK_LIMIT = int(os.getenv("READERS_TRACK_LIMIT", "50"))
LAST_MESSAGES = deque(maxlen=READERS_TRACK_LIMIT)


@client.on(events.NewMessage)
async def handler(event):
    from utils.content_sender import handle_content_link, is_supported_content_url

    if event.out:
        return

    text = event.message.raw_text or ""
    if text.strip() == "🕰️":
        return

    urls = re.findall(r"https?://\S+", text)
    if not urls:
        return

    if not any(is_supported_content_url(url) for url in urls):
        return

    print(
        "Сообщение со ссылкой: "
        f"chat_id={event.chat_id}, sender_id={event.sender_id}, urls={len(urls)}"
    )
    await handle_content_link(event, client, LAST_MESSAGES)


async def main():
    global client
    print(f"Клиент запускается с сессией: {SESSION_NAME}.session")
    from utils.message_readers import update_readers

    session_file = SESSION_NAME if SESSION_NAME.endswith(".session") else f"{SESSION_NAME}.session"

    while True:
        try:
            await client.connect()
            if not await client.is_user_authorized():
                print("Сессия не авторизована. Ожидаю вход через QR...")
                while True:
                    qr_login = await client.qr_login()
                    print(f"QR URL: {qr_login.url}")
                    print(f"QR exp: {qr_login.expires.isoformat()}")
                    try:
                        await qr_login.wait()
                        print("QR авторизация успешно завершена")
                        break
                    except asyncio.TimeoutError:
                        print("QR истек, генерирую новый...")
                        continue
            break
        except AuthKeyDuplicatedError:
            print(
                f"AuthKeyDuplicatedError: перезапускаю сессию локально: {session_file}"
            )
            for suffix in ["", ".journal", ".wal"]:
                path = f"{session_file}{suffix}"
                if os.path.exists(path):
                    os.remove(path)
            client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
            continue
    asyncio.create_task(update_readers(client, LAST_MESSAGES))
    print("Клиент запущен. Ожидаю сообщения...")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
