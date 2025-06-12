import asyncio
import os
import shutil
import re
import subprocess
import json
import traceback
from telethon import functions
import requests

from instagram_handlers import download_instagram_content
from tiktok_handlers import (
    download_tiktok_video,
    download_tiktok_photos_with_audio,
)
from youtube_handler import download_youtube_video
from openai import OpenAI

# Инициализация клиента OpenAI для работы с LLM
openai_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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",
    default_headers={
        "HTTP-Referer": "YOUR_SITE_URL",
        "X-Title": "YOUR_APP_NAME",
    },
)


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

                    messages = message if isinstance(message, list) else [message]

                    for msg in messages:
                        if not msg.id:
                            continue
                        current_readers = await get_readers(
                            client, chat_id, msg.id, sender_id
                        )

                        previous_readers = entry.get("readers", set())

                        if current_readers != previous_readers:
                            await update_message_caption(client, msg, current_readers)
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
    return re.sub(r'[\\/*?:"<>|]', "", name)


def convert_video_to_mp3(video_path, output_path=None):
    """Конвертирует видео в MP3"""
    if output_path is None:
        output_path = os.path.splitext(video_path)[0] + ".mp3"
    try:
        command = [
            "ffmpeg",
            "-i",
            video_path,
            "-q:a",
            "0",
            "-map",
            "a",
            output_path,
            "-y",
        ]
        subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Ошибка конвертации в MP3: {e.stderr.decode()}")
        return None


def convert_video_to_ogg_opus(video_path, output_path=None):
    """Конвертирует видео в OGG с кодеком Opus для голосового сообщения"""
    if output_path is None:
        output_path = os.path.splitext(video_path)[0] + ".ogg"
    try:
        command = [
            "ffmpeg",
            "-i",
            video_path,
            "-c:a",
            "libopus",
            "-b:a",
            "32k",
            "-vn",  # Убираем видео, оставляем только аудио
            output_path,
            "-y",
        ]
        subprocess.run(
            command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        return output_path
    except subprocess.CalledProcessError as e:
        print(f"Ошибка конвертации в OGG Opus: {e.stderr.decode()}")
        return None


async def get_conversion_action(user_input):
    """Определяет действие конвертации через LLM"""
    conversion_prompt = """
    Пользователь запрашивает конвертацию медиа-контента. Определи требуемое действие:
    1. Если пользователь хочет преобразовать видео в аудиофайл (.mp3) - используй "mp3"
    2. Если пользователь хочет преобразовать видео в голосовое сообщение - используй "voice"

    Верни ответ ТОЛЬКО в формате JSON без дополнительных объяснений. Примеры:
    - {{"action": "mp3"}}
    - {{"action": "voice"}}

    Текст запроса пользователя: {user_input}
    """.format(user_input=user_input)

    print(f"Отправляемый промпт:\n{conversion_prompt}")

    try:
        response = openai_client.chat.completions.create(
            model="deepseek/deepseek-chat-v3-0324:free",
            messages=[{"role": "system", "content": conversion_prompt}],
            response_format={"type": "json_object"},
        )

        # Получаем сырой ответ
        raw_response = response.choices[0].message.content
        print(f"Сырой ответ от LLM: {raw_response}")

        # Парсим JSON
        try:
            result = json.loads(raw_response)
            print(f"Парсинг JSON: {result}")

            action = result.get("action")
            print(f"Извлеченное действие: {action}")

            return action
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга JSON: {e}")
            print(f"Содержимое ответа: {raw_response}")
            return None

    except Exception as e:
        print(f"Ошибка при определении действия конвертации: {e}")
        traceback.print_exc()
        return None


async def handle_content_link(event, client, LAST_MESSAGES):
    text = event.message.raw_text
    sender = await event.get_sender()
    sender_id = sender.id
    sender_name = f"@{sender.username}" if sender.username else sender.first_name
    status_message = await client.send_message(event.chat_id, "🕰️")

    # Извлечение URL из сообщения
    urls = re.findall(r"https?://\S+", text)
    if not urls:
        await status_message.delete()
        return
    url = urls[0]

    # Извлечение инструкции пользователя
    instruction = text.replace(url, "").strip()

    try:
        try:
            response = requests.head(url, allow_redirects=True, timeout=5)
            resolved_url = response.url
        except requests.RequestException:
            resolved_url = url

        # Если есть инструкция - обрабатываем конвертацию
        if instruction:
            action = await get_conversion_action(instruction)

            # Проверяем, что действие определено корректно
            if action in ["mp3", "voice"]:
                # Проверяем, что ссылка поддерживает конвертацию
                if (
                    "tiktok.com" in resolved_url
                    or "youtube.com" in resolved_url
                    or "youtu.be" in resolved_url
                ):
                    # Скачиваем видео
                    if "tiktok.com" in resolved_url:
                        file_path, video_title = download_tiktok_video(resolved_url)
                    else:  # YouTube
                        file_path, video_title = download_youtube_video(resolved_url)

                    if not file_path or not os.path.exists(file_path):
                        await client.send_message(
                            event.chat_id, "Не удалось скачать видео для конвертации."
                        )
                        return

                    # Выбираем формат в зависимости от действия
                    if action == "mp3":
                        output_path = convert_video_to_mp3(file_path)
                        if not output_path:
                            await client.send_message(
                                event.chat_id, "Ошибка конвертации в аудио."
                            )
                            return
                        caption = f"{sender_name}\nАудио версия\n{url}"
                        sent_message = await client.send_file(
                            event.chat_id, output_path, caption=caption
                        )
                        LAST_MESSAGES.append(
                            {
                                "chat_id": event.chat_id,
                                "message": sent_message,
                                "sender_id": sender_id,
                                "readers": set(),
                            }
                        )
                    elif action == "voice":
                        output_path = convert_video_to_ogg_opus(file_path)
                        if not output_path:
                            await client.send_message(
                                event.chat_id,
                                "Ошибка конвертации в голосовое сообщение.",
                            )
                            return
                        await client.send_file(
                            event.chat_id, output_path, voice_note=True
                        )  # No caption

                    # Удаляем временные файлы
                    cleanup(file_path)
                    cleanup(output_path)

                    await event.delete()
                    await status_message.delete()
                    return

        # Стандартная обработка контента
        if "tiktok.com" in resolved_url:
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

                return
            else:
                file_path, video_title = download_tiktok_video(resolved_url)
        elif "instagram.com" in resolved_url:
            content = download_instagram_content(resolved_url)
            media = content["media"]
            audio = content["audio"]
            video_title = content["title"]

            if not media:
                await client.send_message(event.chat_id, "Не удалось скачать контент.")
                return

            caption = (
                f"{sender_name}\n{url}"
                if not video_title
                else f"{sender_name}\n{video_title}\n{url}"
            )

            # Store all sent messages for tracking
            sent_messages = []

            # Отправка фото как альбома
            photos = [m["file_path"] for m in media if m["type"] == "photo"]
            if photos:
                message_with_photos = await client.send_file(
                    event.chat_id, photos, caption=caption
                )
                sent_messages.append(message_with_photos)

            # Отправка видео по отдельности
            for m in media:
                if m["type"] == "video":
                    message_with_video = await client.send_file(
                        event.chat_id, m["file_path"], caption=caption
                    )
                    sent_messages.append(message_with_video)

            # Отправка аудио, если есть
            if audio:
                await client.send_file(event.chat_id, audio, caption="")

            # Store all messages for read tracking
            for msg in sent_messages:
                LAST_MESSAGES.append(
                    {
                        "chat_id": event.chat_id,
                        "message": msg,
                        "sender_id": sender_id,
                        "readers": set(),
                    }
                )

            # Очистка
            for m in media:
                cleanup(m["file_path"])
            if audio:
                cleanup(audio)

            return
        else:
            file_path, video_title = None, None

        if not file_path or not os.path.exists(file_path):
            print("Не удалось скачать видео или ссылка не поддерживается.")
            return

        caption = (
            f"{sender_name}\n{url}"
            if not video_title
            else f"{sender_name}\n{video_title}\n{url}"
        )
        message_with_video = await client.send_file(
            event.chat_id, file_path, caption=caption
        )

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
        # Исправление ошибки с выводом некорректного сообщения
        print(e)
        error_msg = f"Произошла ошибка: {str(e)}"
        await client.send_message(event.chat_id, error_msg)
    finally:
        # Автоматическое удаление исходного сообщения с ссылкой
        try:
            await event.delete()
        except Exception as e:
            print(f"Ошибка при удалении сообщения: {e}")
        # Всегда удаляем статусное сообщение
        try:
            await status_message.delete()
        except Exception as e:
            print(f"Ошибка при удалении статусного сообщения: {e}")
