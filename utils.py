import asyncio
import os
import shutil
import re
from telethon import functions
import requests

from instagram_handlers import (
    download_instagram_photos_with_audio,
    download_instagram_video,
)
from tiktok_handlers import (
    download_tiktok_video,
    download_tiktok_photos_with_audio,
)
from youtube_handler import download_youtube_video


async def get_readers(client, chat_id, message_id, sender_id):
    readers = set()
    try:
        result = await client(
            functions.messages.GetMessageReadParticipantsRequest(
                peer=chat_id, msg_id=message_id
            )
        )
        for read_participant in result:
            if read_participant.user_id != sender_id:
                user = await client.get_entity(read_participant.user_id)
                username = f"@{user.username}" if user.username else user.first_name
                readers.add(username)
        return readers
    except Exception as e:
        if "Content of the message was not modified" not in str(e):
            print(f"Ошибка получения списка прочитавших: {e}")
        return readers


async def update_message_caption(client, message, readers):
    try:
        original_caption = message.text or ""
        prefix, sep, existing_readers = original_caption.partition("👤:")
        prefix = prefix.rstrip("\n").strip()

        new_caption = prefix
        readers_str = ""

        if readers:
            sorted_readers = sorted(readers)
            readers_str = f"\n👤: {', '.join(sorted_readers)}"

            existing_normalized = " ".join(existing_readers.strip().split())
            new_normalized = " ".join(readers_str.strip().split())

            if existing_normalized != new_normalized:
                new_caption += readers_str

        original_normalized = " ".join(original_caption.strip().split())
        new_normalized = " ".join(new_caption.strip().split())

        if new_normalized != original_normalized and message.id:
            await message.edit(new_caption)
    except Exception as e:
        if "Message not modified" not in str(e):
            print(f"Error updating caption: {e}")


async def update_readers(client, LAST_MESSAGES):
    while True:
        try:
            for entry in list(LAST_MESSAGES):
                try:
                    chat_id = entry["chat_id"]
                    message = entry["message"]
                    sender_id = entry["sender_id"]
                    if not message.id:
                        continue
                    current_readers = await get_readers(
                        client, chat_id, message.id, sender_id
                    )

                    previous_readers = entry.get("readers", set())

                    if current_readers != previous_readers:
                        await update_message_caption(client, message, current_readers)
                        entry["readers"] = current_readers
                except Exception as e:
                    print(f"Error processing message entry: {e}")
                    continue
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Error in update_readers loop: {e}")
            await asyncio.sleep(10)


def cleanup(cleanup_path):
    if os.path.isdir(cleanup_path):
        shutil.rmtree(cleanup_path, ignore_errors=True)
    elif os.path.exists(cleanup_path):
        os.remove(cleanup_path)


def sanitize_filename(name):
    """Remove invalid characters from filename"""
    return re.sub(r'[\\/*?:"<>|]', "", name)


async def handle_content_link(event, client, LAST_MESSAGES):
    url = event.message.raw_text
    sender = await event.get_sender()
    sender_id = sender.id
    sender_name = f"@{sender.username}" if sender.username else sender.first_name
    status_message = await client.send_message(event.chat_id, "🕰️")
    try:
        try:
            response = requests.head(url, allow_redirects=True, timeout=5)
            resolved_url = response.url
        except requests.RequestException:
            resolved_url = url

        if "youtube.com" in resolved_url or "youtu.be" in resolved_url:
            file_path, video_title = download_youtube_video(resolved_url)
        elif "tiktok.com" in resolved_url:
            if "/photo/" in resolved_url:
                photos_filename, audio_filename, video_title = (
                    download_tiktok_photos_with_audio(resolved_url)
                )

                if not photos_filename:
                    await client.send_message(event.chat_id, "Не удалось скачать фото.")
                    return

                caption = (
                    f"{sender_name}\n{url}"
                    if not video_title
                    else f"{sender_name}\n{video_title}\n{url}"
                )

                message_with_photos = await client.send_file(
                    event.chat_id, photos_filename, caption=caption
                )

                if audio_filename:
                    if video_title:
                        sanitized_title = sanitize_filename(video_title)
                        new_audio_path = os.path.join(
                            os.path.dirname(audio_filename), f"{sanitized_title}.mp3"
                        )
                        os.rename(audio_filename, new_audio_path)
                        audio_filename = new_audio_path

                    await client.send_file(event.chat_id, audio_filename, caption="")

                await event.delete()

                LAST_MESSAGES.append(
                    {
                        "chat_id": event.chat_id,
                        "message": message_with_photos,
                        "sender_id": sender_id,
                        "readers": set(),
                    }
                )

                for file_path in photos_filename:
                    cleanup(file_path)
                if audio_filename:
                    cleanup(audio_filename)

                await status_message.delete()
                return
            else:
                file_path, video_title = download_tiktok_video(resolved_url)
        elif "instagram.com" in resolved_url:
            if "/p/" in resolved_url or "/reel/" in resolved_url:
                photos_filename, audio_filename, video_title = (
                    download_instagram_photos_with_audio(resolved_url)
                )

                if not photos_filename:
                    await client.send_message(event.chat_id, "Не удалось скачать фото.")
                    return

                caption = (
                    f"{sender_name}\n{url}"
                    if not video_title
                    else f"{sender_name}\n{video_title}\n{url}"
                )

                message_with_photos = await client.send_file(
                    event.chat_id, photos_filename, caption=caption
                )

                if audio_filename:
                    if video_title:
                        sanitized_title = sanitize_filename(video_title)
                        new_audio_path = os.path.join(
                            os.path.dirname(audio_filename), f"{sanitized_title}.mp3"
                        )
                        os.rename(audio_filename, new_audio_path)
                        audio_filename = new_audio_path

                    await client.send_file(event.chat_id, audio_filename, caption="")

                await event.delete()

                LAST_MESSAGES.append(
                    {
                        "chat_id": event.chat_id,
                        "message": message_with_photos,
                        "sender_id": sender_id,
                        "readers": set(),
                    }
                )

                for file_path in photos_filename:
                    cleanup(file_path)
                if audio_filename:
                    cleanup(audio_filename)

                await status_message.delete()
                return
            else:
                file_path, video_title = download_instagram_video(resolved_url)
        else:
            file_path, video_title = None, None

        if not file_path or not os.path.exists(file_path):
            await client.send_message(
                event.chat_id, "Не удалось скачать видео или ссылка не поддерживается."
            )
            return

        caption = (
            f"{sender_name}\n{url}"
            if not video_title
            else f"{sender_name}\n{video_title}\n{url}"
        )
        message_with_video = await client.send_file(
            event.chat_id, file_path, caption=caption
        )

        await event.delete()

        LAST_MESSAGES.append(
            {
                "chat_id": event.chat_id,
                "message": message_with_video,
                "sender_id": sender_id,
                "readers": set(),
            }
        )

        cleanup(file_path)

    except Exception as e:
        await client.send_message(event.chat_id, f"Произошла ошибка: {e}")
    finally:
        await status_message.delete()

