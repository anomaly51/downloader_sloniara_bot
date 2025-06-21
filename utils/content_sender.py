import os
import re
import requests
import asyncio
from .file_utils import cleanup, sanitize_filename
from .content_downloader import download_tiktok, download_youtube, download_instagram
from .openai_client import get_openai_client


async def shorten_title(title):
    """Сокращает заголовок до 100 символов с помощью DeepSeek."""
    client = get_openai_client()
    prompt = f"Верни ТОЛЬКО сокращённый текст до 100 символов. ТОЛЬКО буквы и пробелы. НИКАКИХ других символов, слов, знаков, эмодзи, форматирования, комментариев или любых добавлений. Сокращай ТОЛЬКО следующий текст, ничего не придумывай и не добавляй: ==={title}==="
    try:
        response = client.completions.create(
            model="deepseek/deepseek-chat-v3-0324:free",
            prompt=prompt,
        )
        shortened_title = response.choices[0].text.strip()
        return shortened_title
    except Exception as e:
        print(f"Ошибка при сокращении заголовка: {e}")
        return "audio"  # Возвращаем "audio" вместо ошибки для надёжности


async def update_title(client, chat_id, message, original_title, url, sender_name):
    """Сокращает заголовок и обновляет сообщение в Telegram."""
    shortened_title = await shorten_title(original_title)
    new_caption = f"{sender_name}\n{shortened_title}\n{url}"
    try:
        if isinstance(message, list):
            await message[0].edit(new_caption)
        else:
            await message.edit(new_caption)
    except Exception as e:
        print(f"Ошибка при редактировании сообщения: {e}")


async def send_content(client, chat_id, content, caption, sender_id, LAST_MESSAGES):
    """Отправляет контент в чат и добавляет в LAST_MESSAGES."""
    if content["type"] == "photos":
        message = await client.send_file(chat_id, content["files"], caption=caption)
        if content["audio"]:
            sanitized_title = (
                sanitize_filename(content["title"]) if content["title"] else "audio"
            )
            # Ограничиваем длину sanitized_title до 100 символов
            sanitized_title = sanitized_title[:100]
            new_audio_path = os.path.join(
                os.path.dirname(content["audio"]), f"{sanitized_title}.mp3"
            )
            try:
                os.rename(content["audio"], new_audio_path)
            except OSError as e:
                print(f"Ошибка при переименовании аудиофайла: {e}")
                new_audio_path = content[
                    "audio"
                ]  # Используем оригинальный путь в случае ошибки
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
    return message


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

        title = content.get("title", "")
        if len(title) > 100:
            caption = f"{sender_name}\n⏱️\n{url}"
            message = await send_content(
                client, event.chat_id, content, caption, sender_id, LAST_MESSAGES
            )
            asyncio.create_task(
                update_title(client, event.chat_id, message, title, url, sender_name)
            )
        else:
            caption = f"{sender_name}\n{title + '\n' if title else ''}{url}"
            await send_content(
                client, event.chat_id, content, caption, sender_id, LAST_MESSAGES
            )

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

