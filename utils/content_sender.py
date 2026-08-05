import os
import re
import asyncio
import traceback
from html import escape, unescape
from urllib.parse import urlparse, urlunparse
from .file_utils import cleanup, sanitize_filename
from .content_converters import convert_video_to_mp3, convert_video_to_ogg_opus
from .openai_client import get_openai_client
from .direct_downloader import download_direct, is_instagram_url
from .proxy_bot_downloader import (
    download_via_proxy_bot,
    get_proxy_debug_log_path,
    is_proxy_bot_username,
)
from .message_readers import register_tracked_message, update_tracked_base_caption

SEND_CONTENT_TIMEOUT = int(os.getenv("SEND_CONTENT_TIMEOUT", "180"))


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
        f"Сгенерируй короткое (до 50 символов), Kоксичное сообщение с грубостями для @{tagged_user}, "
        f"чтобы привлечь его внимание к этому контенту. Сообщение должно быть неформальным, передавать вайб и смысл такой как в инструкции"
        f"инструкции, перефразируя их максимально близко к оригиналу. "
        f"\n\nКонтекст инструкции: {instruction[:200] if instruction else 'нет инструкции'}"
        f"\n\nПример: 'Эй @user, смотри, твой кумир - лох позорный!'"
        f"\n\nТребования:"
        f"\n1. Только текст без кавычек и спецсимволов"
        f"\n2. Не более 50 символов"
        f"\n3. Начинай с @{tagged_user}"
        f"\n4. Учитывай тип контента и вайб инструкции"
        f"\n5. Сохраняй смысл и тон инструкции, перефразируя"
        f"\n6. Отправь только текст обращения. Не пиши ничего лишнего"
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


async def update_title(
    client, chat_id, message, original_title, caption_link, sender_name, LAST_MESSAGES
):
    """Сокращает заголовок и обновляет сообщение в Telegram, сохраняя список просмотров и удаляя временный индикатор."""
    try:
        shortened_title = await shorten_title(original_title)
        if isinstance(message, list):
            msg = message[0]  # Для альбома берём первое сообщение
        else:
            msg = message
        current_caption = msg.raw_text or ""  # Получаем подпись без markdown/entities

        # Разделяем подпись на строки
        lines = current_caption.split("\n")
        if len(lines) >= 3:
            # Первые две строки: sender_name и заголовок (или ⏱️)
            sender_line = lines[0]
            title_line = lines[1]
            # Остальные строки могут содержать список просмотров
            viewers_lines = lines[3:] if len(lines) > 3 else []

            # Если вторая строка содержит ⏱️, заменяем её на shortened_title
            if "⏱️" in title_line:
                title_line = shortened_title

            # Формируем новую подпись
            base_caption = f"{sender_line}\n{title_line}\n{unescape(caption_link)}"
            new_caption = (
                f"{escape(sender_line)}\n{escape(title_line)}\n{caption_link}"
            )
            if viewers_lines:
                viewers_part = "\n".join(escape(line) for line in viewers_lines)
                new_caption += f"\n{viewers_part}"
        else:
            # Если подпись не соответствует ожидаемому формату, обновляем её
            base_caption = f"{sender_name}\n{shortened_title}\n{unescape(caption_link)}"
            new_caption = (
                f"{escape(sender_name)}\n{escape(shortened_title)}\n{caption_link}"
            )

        await msg.edit(new_caption, parse_mode="html")
        update_tracked_base_caption(LAST_MESSAGES, message, base_caption)
    except Exception as e:
        print(f"Ошибка при редактировании сообщения: {e}")


async def send_content(client, chat_id, content, caption, sender_id, LAST_MESSAGES):
    """Отправляет контент в чат и добавляет в LAST_MESSAGES для отслеживания просмотров."""
    message = None
    try:
        if content["type"] == "photos":
            print(f"Отправляю photos в чат {chat_id}")
            message = await client.send_file(
                chat_id, content["files"], caption=caption, parse_mode="html"
            )
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
            register_tracked_message(
                LAST_MESSAGES, chat_id, message, sender_id, caption
            )

        elif content["type"] == "video":
            print(f"Отправляю video в чат {chat_id}: {content.get('file')}")
            message = await client.send_file(
                chat_id, content["file"], caption=caption, parse_mode="html"
            )
            register_tracked_message(
                LAST_MESSAGES, chat_id, message, sender_id, caption
            )

        elif content["type"] == "audio":
            print(f"Отправляю audio в чат {chat_id}: {content.get('file')}")
            message = await client.send_file(
                chat_id, content["file"], caption=caption, parse_mode="html"
            )
            register_tracked_message(
                LAST_MESSAGES, chat_id, message, sender_id, caption
            )

        elif content["type"] == "voice":
            # Исправлено: добавлена подпись для голосовых сообщений
            print(f"Отправляю voice в чат {chat_id}: {content.get('file')}")
            message = await client.send_file(
                chat_id,
                content["file"],
                voice_note=True,
                caption=caption,
                parse_mode="html",
            )
            register_tracked_message(
                LAST_MESSAGES, chat_id, message, sender_id, caption
            )

        elif content["type"] == "telegram_media":
            print(
                "Отправляю telegram_media в чат "
                f"{chat_id}: {content.get('source_content_type')}"
            )
            message = await client.send_file(
                chat_id, content["media"], caption=caption, parse_mode="html"
            )
            register_tracked_message(
                LAST_MESSAGES, chat_id, message, sender_id, caption
            )

        elif content["type"] == "mixed":
            photos = [m["file_path"] for m in content["media"] if m["type"] == "photo"]
            videos = [m["file_path"] for m in content["media"] if m["type"] == "video"]

            if photos:
                message = await client.send_file(
                    chat_id, photos, caption=caption, parse_mode="html"
                )
                register_tracked_message(
                    LAST_MESSAGES, chat_id, message, sender_id, caption
                )

            for video in videos:
                message = await client.send_file(
                    chat_id, video, caption=caption, parse_mode="html"
                )
                register_tracked_message(
                    LAST_MESSAGES, chat_id, message, sender_id, caption
                )

            if content.get("audio"):
                await client.send_file(chat_id, content["audio"], caption="")

        print(f"Контент отправлен в чат {chat_id}")
        return message

    except Exception as e:
        print(f"Ошибка при отправке контента: {e}")
        raise


def apply_conversion_if_needed(content, conversion_instruction):
    if not conversion_instruction or not content or content.get("type") != "video":
        return content

    source_file = content.get("file")
    if not source_file:
        return content

    if conversion_instruction == "mp3":
        output_path = convert_video_to_mp3(source_file)
        if output_path:
            return {
                "type": "audio",
                "file": output_path,
                "title": content.get("title", ""),
            }
    elif conversion_instruction == "voice":
        output_path = convert_video_to_ogg_opus(source_file)
        if output_path:
            return {
                "type": "voice",
                "file": output_path,
                "title": content.get("title", ""),
            }

    return content


def cleanup_content(content):
    """Очищает временные файлы после отправки."""
    try:
        if not content:
            return

        if content.get("file"):
            cleanup(content["file"])

        if content.get("files"):
            for file in content["files"]:
                cleanup(file)

        if content.get("audio"):
            cleanup(content["audio"])

        media = content.get("media")
        if isinstance(media, list):
            for m in media:
                if isinstance(m, dict):
                    cleanup(m.get("file_path", ""))

        if content.get("_workdir"):
            cleanup(content["_workdir"])
    except Exception as e:
        print(f"Ошибка при очистке файлов: {e}")


def shorten_tiktok_url(original_url, resolved_url):
    """Возвращает короткую ссылку TikTok без tracking-параметров."""
    source_url = resolved_url or original_url
    parsed = urlparse(source_url)
    host = parsed.netloc.lower()

    if "tiktok.com" not in host:
        return original_url

    canonical_match = re.search(
        r"^/(@[^/]+)/(video|photo)/(\d+)", parsed.path
    )
    if canonical_match:
        user, content_type, content_id = canonical_match.groups()
        return f"https://www.tiktok.com/{user}/{content_type}/{content_id}"

    # Keep TikTok short domains short, just remove query/fragment noise.
    original_parsed = urlparse(original_url)
    if "tiktok.com" in original_parsed.netloc.lower():
        clean_path = original_parsed.path.rstrip("/")
        if clean_path:
            return urlunparse(
                (
                    original_parsed.scheme or "https",
                    original_parsed.netloc,
                    clean_path,
                    "",
                    "",
                    "",
                )
            )

    clean_path = parsed.path.rstrip("/")
    if clean_path:
        return urlunparse(("https", parsed.netloc, clean_path, "", "", ""))

    return original_url


def format_caption_link(display_url):
    """Возвращает обычную видимую ссылку без скрытой HTML-гиперссылки."""
    return escape(display_url)


def is_supported_content_url(url):
    host = urlparse(url).netloc.lower()
    supported_hosts = (
        "tiktok.com",
        "youtube.com",
        "youtu.be",
        "instagram.com",
    )

    return any(
        host == domain or host.endswith(f".{domain}") for domain in supported_hosts
    )


async def handle_content_link(event, client, LAST_MESSAGES):
    """Основная функция обработки ссылки на контент."""
    chat = await event.get_chat()
    if is_proxy_bot_username(getattr(chat, "username", "")):
        return

    text = event.message.raw_text
    sender = await event.get_sender()
    if is_proxy_bot_username(getattr(sender, "username", "")):
        return

    sender_id = sender.id
    sender_name = f"@{sender.username}" if sender.username else sender.first_name
    status_message = None
    delete_original = False

    try:
        urls = re.findall(r"https?://\S+", text)
        if not urls:
            return

        url = urls[0]
        instruction = text.replace(url, "").strip()
        print(f"Инструкция: {instruction}")

        if not is_supported_content_url(url):
            return

        delete_original = True

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

        display_url = url
        if is_instagram_url(url):
            display_url = url.split("?", 1)[0].rstrip("/")
        display_url = shorten_tiktok_url(url, display_url)
        caption_link = format_caption_link(display_url)

        status_message = await client.send_message(event.chat_id, "🕰️")

        content = await download_direct(url)
        if not content:
            content = await download_via_proxy_bot(
                client,
                url,
                reason="proxy-only downloader",
                download_media=bool(conversion_instruction),
            )
        content = apply_conversion_if_needed(content, conversion_instruction)

        if not content:
            if status_message:
                await status_message.delete()
                status_message = None
            await client.send_message(event.chat_id, "Не удалось скачать контент.")
            print(
                "Подробности fallback-прокси: "
                f"{get_proxy_debug_log_path()}"
            )
            return

        # Готовим заголовок
        title = content.get("title", "") or ""

        # Всегда отправляем временный индикатор для длинных заголовков
        if len(title) > 200:
            initial_caption = f"{escape(sender_name)}\n⏱️\n{caption_link}"
        else:
            initial_caption = (
                f"{escape(sender_name)}\n{escape(title)}\n{caption_link}"
                if title
                else f"{escape(sender_name)}\n{caption_link}"
            )

        # Отправляем контент с временным заголовком
        message = await asyncio.wait_for(
            send_content(
                client,
                event.chat_id,
                content,
                initial_caption,
                sender_id,
                LAST_MESSAGES,
            ),
            timeout=SEND_CONTENT_TIMEOUT,
        )

        # Обновляем длинные заголовки асинхронно
        if len(title) > 200:
            asyncio.create_task(
                update_title(
                    client,
                    event.chat_id,
                    message,
                    title,
                    caption_link,
                    sender_name,
                    LAST_MESSAGES,
                )
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
        if status_message:
            try:
                await status_message.delete()
            except:
                pass
            status_message = None
        await client.send_message(event.chat_id, error_msg)
    finally:
        if delete_original:
            try:
                await event.delete()
            except:
                pass

        if status_message:
            try:
                await status_message.delete()
            except:
                pass
