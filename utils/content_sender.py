import os
import re
import requests
from .file_utils import cleanup, sanitize_filename
from .content_downloader import download_tiktok, download_youtube, download_instagram


async def send_content(client, chat_id, content, caption, sender_id, LAST_MESSAGES):
    """Отправляет контент в чат и добавляет в LAST_MESSAGES."""
    if content["type"] == "photos":
        message = await client.send_file(chat_id, content["files"], caption=caption)
        if content["audio"]:
            sanitized_title = (
                sanitize_filename(content["title"]) if content["title"] else "audio"
            )
            new_audio_path = os.path.join(
                os.path.dirname(content["audio"]), f"{sanitized_title}.mp3"
            )
            os.rename(content["audio"], new_audio_path)
            await client.send_file(chat_id, new_audio_path)
        LAST_MESSAGES.append(
            {
                "chat_id": chat_id,
                "message": message,
                "sender_id": sender_id,
                "readers": set(),
            }
        )
    elif content["type"] == "video":
        message = await client.send_file(chat_id, content["file"], caption=caption)
        LAST_MESSAGES.append(
            {
                "chat_id": chat_id,
                "message": message,
                "sender_id": sender_id,
                "readers": set(),
            }
        )
    elif content["type"] == "audio":
        message = await client.send_file(chat_id, content["file"], caption=caption)
        LAST_MESSAGES.append(
            {
                "chat_id": chat_id,
                "message": message,
                "sender_id": sender_id,
                "readers": set(),
            }
        )
    elif content["type"] == "voice":
        await client.send_file(chat_id, content["file"], voice_note=True)
    elif content["type"] == "mixed":
        photos = [m["file_path"] for m in content["media"] if m["type"] == "photo"]
        videos = [m["file_path"] for m in content["media"] if m["type"] == "video"]
        if photos:
            message = await client.send_file(chat_id, photos, caption=caption)
            LAST_MESSAGES.append(
                {
                    "chat_id": chat_id,
                    "message": message,
                    "sender_id": sender_id,
                    "readers": set(),
                }
            )
        for video in videos:
            message = await client.send_file(chat_id, video, caption=caption)
            LAST_MESSAGES.append(
                {
                    "chat_id": chat_id,
                    "message": message,
                    "sender_id": sender_id,
                    "readers": set(),
                }
            )
        if content["audio"]:
            await client.send_file(chat_id, content["audio"], caption="")


def cleanup_content(content):
    """Очищает временные файлы после отправки."""
    if "file" in content and content["file"]:
        cleanup(content["file"])
    elif "files" in content and content["files"]:
        for file in content["files"]:
            cleanup(file)
    if "audio" in content and content["audio"]:
        cleanup(content["audio"])
    if "media" in content and content["media"]:
        for m in content["media"]:
            cleanup(m["file_path"])


async def handle_content_link(event, client, LAST_MESSAGES):
    """Основная функция обработки ссылки на контент."""
    text = event.message.raw_text
    sender = await event.get_sender()
    sender_id = sender.id
    sender_name = f"@{sender.username}" if sender.username else sender.first_name
    status_message = await client.send_message(event.chat_id, "🕰️")

    try:
        urls = re.findall(r"https?://\S+", text)
        if not urls:
            await status_message.delete()
            return
        url = urls[0]
        instruction = text.replace(url, "").strip()

        try:
            response = requests.head(url, allow_redirects=True, timeout=5)
            resolved_url = response.url
        except requests.RequestException:
            resolved_url = url

        # Определение платформы и вызов обработчика с помощью if-elif
        if "tiktok.com" in resolved_url:
            content = await download_tiktok(resolved_url, instruction)
        elif "instagram.com" in resolved_url:
            content = await download_instagram(resolved_url, instruction)
        elif "youtube.com" in resolved_url or "youtu.be" in resolved_url:
            content = await download_youtube(resolved_url, instruction)
        else:
            await client.send_message(event.chat_id, "Платформа не поддерживается.")
            return

        if not content:
            await client.send_message(event.chat_id, "Не удалось скачать контент.")
            return

        # Формирование подписи
        caption = (
            f"{sender_name}\n{url}"
            if not content.get("title")
            else f"{sender_name}\n{content['title']}\n{url}"
        )

        # Отправка контента
        await send_content(
            client, event.chat_id, content, caption, sender_id, LAST_MESSAGES
        )

        # Очистка
        cleanup_content(content)

    except Exception as e:
        print(e)
        error_msg = f"Произошла ошибка: {str(e)}"
        await client.send_message(event.chat_id, error_msg)
    finally:
        try:
            await event.delete()
        except Exception as e:
            print(f"Ошибка при удалении сообщения: {e}")
        try:
            await status_message.delete()
        except Exception as e:
            print(f"Ошибка при удалении статусного сообщения: {e}")
