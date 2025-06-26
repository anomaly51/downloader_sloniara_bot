import os
import re
import requests
import asyncio
import traceback
from .file_utils import cleanup, sanitize_filename
from .content_downloader import download_tiktok, download_youtube, download_instagram
from .openai_client import get_openai_client


async def generate_personalized_message(
    sender_name, tagged_user, content_type, instruction
):
    """Генерирует персонализированное сообщение через LLM."""
    client = get_openai_client()

    content_type_map = {
        "audio": "аудио",
        "voice": "голосовое сообщение",
        "video": "видео",
        "photos": "фото",
        "mixed": "контент",
    }

    content_desc = content_type_map.get(content_type, "контент")

    prompt = (
        f"Пользователь {sender_name} отправил {content_desc} и отметил @{tagged_user}. "
        f"Сгенерируй короткое (до 50 символов), максимально токсичное сообщение с грубостями для @{tagged_user}, "
        f"чтобы привлечь его внимание к этому контенту. Сообщение должно быть неформальным, передавать вайб и смысл "
        f"инструкции, перефразируя их максимально близко к оригиналу. "
        f"\n\nКонтекст инструкции: {instruction[:200] if instruction else 'нет инструкции'}"
        f"\n\nПример: 'Эй @user, смотри, твой кумир - лох позорный!'"
        f"\n\nТребования:"
        f"\n1. Только текст без кавычек и спецсимволов"
        f"\n2. Не более 50 символов"
        f"\n3. Начинай с @{tagged_user}"
        f"\n4. Учитывай тип контента и вайб инструкции"
        f"\n5. Сохраняй смысл и тон инструкции, перефразируя"
        f"\n6. Отправь только текст обращения"
    )

    try:
        response = client.completions.create(
            model="deepseek/deepseek-chat", prompt=prompt, max_tokens=50
        )
        message = response.choices[0].text.strip()

        # Убедимся, что сообщение начинается с тега пользователя
        if not message.startswith(f"@{tagged_user}"):
            return f"@{tagged_user}, {message}"
        return message
    except Exception as e:
        print(f"Ошибка генерации сообщения: {e}")
        return f"Эй, @{tagged_user}, смотри этот {content_desc}!"


async def shorten_title(title):
    """Сокращает заголовок до 100 символов с помощью DeepSeek."""
    if not title:
        return ""

    client = get_openai_client()
    prompt = f"Верни ТОЛЬКО сокращённый текст до 100 символов. ТОЛЬКО буквы и пробелы. НИКАКИХ других символов, слов, знаков, эмодзи, форматирования, комментариев или любых добавлений. Сокращай ТОЛЬКО следующий текст, ничего не придумывай и не добавляй: ==={title}==="

    try:
        response = client.completions.create(
            model="deepseek/deepseek-chat",
            prompt=prompt,
        )
        return response.choices[0].text.strip()[:100]
    except Exception as e:
        print(f"Ошибка при сокращении заголовка: {e}")
        return title[:100]


async def update_title(client, chat_id, message, original_title, url, sender_name):
    """Сокращает заголовок и обновляет сообщение в Telegram, сохраняя список просмотров и удаляя временный индикатор."""
    try:
        shortened_title = await shorten_title(original_title)
        if isinstance(message, list):
            msg = message[0]  # Для альбома берём первое сообщение
        else:
            msg = message
        current_caption = msg.text or ""  # Получаем текущую подпись

        # Разделяем подпись на строки
        lines = current_caption.split("\n")
        if len(lines) >= 3:
            # Первые две строки: sender_name и заголовок (или ⏱️)
            sender_line = lines[0]
            title_line = lines[1]
            url_line = lines[2]
            # Остальные строки могут содержать список просмотров
            viewers_lines = lines[3:] if len(lines) > 3 else []

            # Если вторая строка содержит ⏱️, заменяем её на shortened_title
            if "⏱️" in title_line:
                title_line = shortened_title

            # Формируем новую подпись
            new_caption = f"{sender_line}\n{title_line}\n{url_line}"
            if viewers_lines:
                viewers_part = "\n".join(viewers_lines)
                new_caption += f"\n{viewers_part}"
        else:
            # Если подпись не соответствует ожидаемому формату, обновляем её
            new_caption = f"{sender_name}\n{shortened_title}\n{url}"

        await msg.edit(new_caption)
    except Exception as e:
        print(f"Ошибка при редактировании сообщения: {e}")


async def send_content(client, chat_id, content, caption, sender_id, LAST_MESSAGES):
    """Отправляет контент в чат и добавляет в LAST_MESSAGES для отслеживания просмотров."""
    message = None
    try:
        if content["type"] == "photos":
            message = await client.send_file(chat_id, content["files"], caption=caption)
            if content.get("audio"):
                sanitized_title = sanitize_filename(content.get("title", "audio"))[:100]
                new_audio_path = os.path.join(
                    os.path.dirname(content["audio"]), f"{sanitized_title}.mp3"
                )
                try:
                    os.rename(content["audio"], new_audio_path)
                except OSError:
                    new_audio_path = content["audio"]
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
            # Исправлено: добавлена подпись для голосовых сообщений
            message = await client.send_file(
                chat_id, content["file"], voice_note=True, caption=caption
            )
            LAST_MESSAGES.append(
                {
                    "chat_id": chat_id,
                    "message": message,
                    "sender_id": sender_id,
                    "readers": set(),
                }
            )

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

            if content.get("audio"):
                await client.send_file(chat_id, content["audio"], caption="")

        return message

    except Exception as e:
        print(f"Ошибка при отправке контента: {e}")
        raise


def cleanup_content(content):
    """Очищает временные файлы после отправки."""
    try:
        if content.get("file"):
            cleanup(content["file"])

        if content.get("files"):
            for file in content["files"]:
                cleanup(file)

        if content.get("audio"):
            cleanup(content["audio"])

        if content.get("media"):
            for m in content["media"]:
                cleanup(m.get("file_path", ""))
    except Exception as e:
        print(f"Ошибка при очистке файлов: {e}")


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
        print(f"Инструкция: {instruction}")

        # Извлекаем тегнутых пользователей
        tagged_users = re.findall(r"@([\w\d_]+)", instruction)
        tagged_user = tagged_users[0] if tagged_users else None

        # Определяем тип конвертации
        instruction_lower = instruction.lower()
        conversion_instruction = None

        if "mp3" in instruction_lower or "аудио" in instruction_lower:
            conversion_instruction = "mp3"
        elif (
            "voice" in instruction_lower
            or "гс" in instruction_lower
            or "голос" in instruction_lower
        ):
            conversion_instruction = "voice"

        print(f"Команда конвертации: {conversion_instruction}")

        try:
            response = requests.head(url, allow_redirects=True, timeout=10)
            resolved_url = response.url
        except requests.RequestException:
            resolved_url = url

        # Скачиваем контент
        if "tiktok.com" in resolved_url:
            content = await download_tiktok(resolved_url, conversion_instruction)
        elif "instagram.com" in resolved_url:
            content = await download_instagram(resolved_url, conversion_instruction)
        elif "youtube.com" in resolved_url or "youtu.be" in resolved_url:
            content = await download_youtube(resolved_url, conversion_instruction)
        else:
            await client.send_message(event.chat_id, "Платформа не поддерживается.")
            await status_message.delete()
            return

        if not content:
            await client.send_message(event.chat_id, "Не удалось скачать контент.")
            await status_message.delete()
            return

        # Готовим заголовок
        title = content.get("title", "") or ""

        # Всегда отправляем временный индикатор для длинных заголовков
        if len(title) > 200:
            initial_caption = f"{sender_name}\n⏱️\n{url}"
        else:
            initial_caption = (
                f"{sender_name}\n{title}\n{url}" if title else f"{sender_name}\n{url}"
            )

        # Отправляем контент с временным заголовком
        message = await send_content(
            client, event.chat_id, content, initial_caption, sender_id, LAST_MESSAGES
        )

        # Обновляем длинные заголовки асинхронно
        if len(title) > 200:
            asyncio.create_task(
                update_title(client, event.chat_id, message, title, url, sender_name)
            )

        # Отправляем персонализированное сообщение для тегнутого пользователя
        if tagged_user:
            personalized_message = await generate_personalized_message(
                sender_name, tagged_user, content["type"], instruction
            )

            if isinstance(message, list) and message:
                message_id = message[0].id
            elif hasattr(message, "id"):
                message_id = message.id
            else:
                message_id = None

            if message_id:
                await client.send_message(
                    event.chat_id, personalized_message, reply_to=message_id
                )
            else:
                await client.send_message(event.chat_id, personalized_message)

        # Очищаем временные файлы
        cleanup_content(content)

    except Exception as e:
        error_trace = traceback.format_exc()
        print(f"Критическая ошибка: {error_trace}")

        error_msg = "Произошла ошибка при обработке контента"
        await client.send_message(event.chat_id, error_msg)
    finally:
        try:
            await event.delete()
        except:
            pass

        try:
            await status_message.delete()
        except:
            pass
