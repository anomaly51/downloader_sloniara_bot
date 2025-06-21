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
        f"Сгенерируй короткое (до 50 символов), дружеское и привлекательное сообщение для @{tagged_user}, "
        f"чтобы привлечь его внимание к этому контенту. Сообщение должно быть неформальным и начинаться с обращения к @{tagged_user}."
        f"\n\nКонтекст инструкции: {instruction[:200] if instruction else 'нет инструкции'}"
        "\n\nПримеры: 'Эй @user, смотри что нашел!', 'Привет @user, специально для тебя!'"
        "\n\nТребования:"
        "\n1. Только текст без кавычек и спецсимволов"
        "\n2. Не более 50 символов"
        "\n3. Обязательно начинай с @username"
        "\n4. Учитывай тип контента и контекст инструкции"
    )

    try:
        response = client.completions.create(
            model="deepseek/deepseek-chat-v3-0324:free", prompt=prompt, max_tokens=50
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
            model="deepseek/deepseek-chat-v3-0324:free",
            prompt=prompt,
        )
        return response.choices[0].text.strip()[:100]
    except Exception as e:
        print(f"Ошибка при сокращении заголовка: {e}")
        return title[:100]


async def update_title(client, chat_id, message, original_title, url, sender_name):
    """Сокращает заголовок и обновляет сообщение в Telegram."""
    try:
        shortened_title = await shorten_title(original_title)
        new_caption = f"{sender_name}\n{shortened_title}\n{url}"

        if isinstance(message, list):
            await message[0].edit(new_caption)
        else:
            await message.edit(new_caption)
    except Exception as e:
        print(f"Ошибка при редактировании сообщения: {e}")


async def send_content(client, chat_id, content, caption, sender_id, LAST_MESSAGES):
    """Отправляет контент в чат и добавляет в LAST_MESSAGES."""
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

        elif content["type"] == "video":
            message = await client.send_file(chat_id, content["file"], caption=caption)

        elif content["type"] == "audio":
            message = await client.send_file(chat_id, content["file"], caption=caption)

        elif content["type"] == "voice":
            message = await client.send_file(chat_id, content["file"], voice_note=True)

        elif content["type"] == "mixed":
            photos = [m["file_path"] for m in content["media"] if m["type"] == "photo"]
            videos = [m["file_path"] for m in content["media"] if m["type"] == "video"]

            if photos:
                message = await client.send_file(chat_id, photos, caption=caption)

            for video in videos:
                message = await client.send_file(chat_id, video, caption=caption)

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

        # ИСПРАВЛЕНИЕ: Всегда отправляем временный индикатор для длинных заголовков
        if len(title) > 100:
            # Для длинных заголовков используем временный индикатор
            initial_caption = f"{sender_name}\n⏱️\n{url}"
        else:
            # Для коротких заголовков отправляем сразу окончательный вариант
            initial_caption = (
                f"{sender_name}\n{title}\n{url}" if title else f"{sender_name}\n{url}"
            )

        # Отправляем контент с временным заголовком
        message = await send_content(
            client, event.chat_id, content, initial_caption, sender_id, LAST_MESSAGES
        )

        # Обновляем длинные заголовки асинхронно
        if len(title) > 100:
            asyncio.create_task(
                update_title(client, event.chat_id, message, title, url, sender_name)
            )

        # Отправляем персонализированное сообщение для тегнутого пользователя
        if tagged_user:
            # Генерируем уникальное сообщение через LLM
            personalized_message = await generate_personalized_message(
                sender_name, tagged_user, content["type"], instruction
            )

            # Определяем ID сообщения для ответа
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

