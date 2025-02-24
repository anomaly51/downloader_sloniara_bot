import pyktok as pyk
import os
import json
import re
import shutil
import asyncio
from collections import deque
from telethon import TelegramClient, events, functions
# Import handlers
from instagram_handler import download_instagram_video
from tiktok_handler import download_tiktok_video
from youtube_handler import download_youtube_video

# Данные API пользователя
api_id = 24669563
api_hash = "2bab5e995b6ea8028921490a3271aded"
phone_number = "+380974040286"

client = TelegramClient('user', api_id, api_hash)

last_messages = deque(maxlen=5)

async def update_readers():
    """Обновляет список пользователей, которые прочитали последние отправленные сообщения."""
    while True:
        for entry in list(last_messages):
            chat_id = entry['chat_id']
            message = entry['message']
            sender_id = entry['sender_id']
            readers = set()

            try:
                # Запрашиваем список пользователей, которые прочитали сообщение
                result = await client(functions.messages.GetMessageReadParticipantsRequest(
                    peer=chat_id,
                    msg_id=message.id
                ))

                # Добавляем пользователей в список, исключая отправителя
                for read_participant in result:
                    if read_participant.user_id != sender_id:
                        user = await client.get_entity(read_participant.user_id)
                        username = f"@{user.username}" if user.username else user.first_name
                        if username not in readers:
                            readers.add(username)

                # Обновляем сообщение только при изменении текста
                new_caption = message.text.split("👤:")[0].strip()
                if readers:
                    new_caption += f"\n👤: {', '.join(readers)}"
                if new_caption != message.text:
                    await message.edit(new_caption)
            except Exception as e:
                if "Content of the message was not modified" not in str(e):
                    print(f"Ошибка обновления списка прочитавших: {e}")
        await asyncio.sleep(10)  # Обновляем каждые 10 секунд

async def handle_video_link(event):
    url = event.message.raw_text
    sender = await event.get_sender()
    sender_id = sender.id
    sender_name = f"@{sender.username}" if sender.username else sender.first_name

    # Отправляем сообщение о загрузке
    status_message = await client.send_message(event.chat_id, "🕰️")

    try:
        file_path, video_title = None, None

        if "youtube.com" in url or "youtu.be" in url:
            file_path, video_title = download_youtube_video(url)
        elif "tiktok.com" in url:
            file_path, video_title = download_tiktok_video(url)
        elif "instagram.com" in url:
            file_path, video_title = download_instagram_video(url)
        else:
            await client.send_message(event.chat_id, "Ссылка не поддерживается.")
            return

        if file_path:
            # Формируем сообщение с переносом строки между @username и ссылкой
            caption = f"{sender_name}\n{url}" if not video_title else f"{sender_name}\n{video_title}\n{url}"
            
            message_with_video = await client.send_file(event.chat_id, file_path, caption=caption)
            os.remove(file_path)  # Удаляем файл после отправки видео
            if "instagram_download" in file_path:
                shutil.rmtree('./instagram_download')

            # Удаляем сообщение пользователя после успешной отправки видео
            await event.delete()

            # Добавляем сообщение в список последних
            last_messages.append({
                'chat_id': event.chat_id,
                'message': message_with_video,
                'sender_id': sender_id
            })
    except Exception as e:
        await client.send_message(event.chat_id, f"Произошла ошибка: {e}")
    finally:
        await status_message.delete()

@client.on(events.NewMessage(pattern=r'http[s]?://[^\s]+'))
async def handler(event):
    await handle_video_link(event)

async def main():
    print("Клиент запускается1")
    asyncio.create_task(update_readers())
    print("Клиент запускается")
    await client.start(phone=phone_number)
    print("Клиент запущен. Ожидаю сообщения...")
    await client.run_until_disconnected()

print("Клиент запускается2")
asyncio.run(main())