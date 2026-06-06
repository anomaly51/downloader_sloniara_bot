import asyncio
import os
import time
from html import escape, unescape
from telethon import functions

READERS_LOOP_SLEEP = float(os.getenv("READERS_LOOP_SLEEP", "1"))
READERS_TRACK_TTL = int(os.getenv("READERS_TRACK_TTL", "7200"))
READERS_CAPTION_LIMIT = int(os.getenv("READERS_CAPTION_LIMIT", "950"))
READERS_MAX_FAILURES = int(os.getenv("READERS_MAX_FAILURES", "10"))


def _normalize_text(text):
    return " ".join((text or "").strip().split())


def _message_list(message):
    if isinstance(message, list):
        return [msg for msg in message if getattr(msg, "id", None)]
    return [message] if getattr(message, "id", None) else []


def _display_message(messages):
    return messages[0] if messages else None


def _strip_readers_line(caption):
    prefix, _, _ = (caption or "").partition("👤:")
    return prefix.rstrip("\n").strip()


def _plain_caption(caption):
    return _strip_readers_line(unescape(caption or ""))


def _caption_from_message(message):
    if not message:
        return ""
    return _strip_readers_line(getattr(message, "raw_text", "") or "")


def _reader_poll_interval(age, changed=False):
    if changed:
        return 2
    if age < 120:
        return 2
    if age < 900:
        return 5
    if age < 3600:
        return 15
    return 45


def _compose_caption(base_caption, readers):
    base_caption = (base_caption or "").rstrip()
    sorted_readers = sorted(readers, key=lambda value: value.lower())

    if not sorted_readers:
        return base_caption

    if len(base_caption) > READERS_CAPTION_LIMIT - 80:
        base_caption = f"{base_caption[:READERS_CAPTION_LIMIT - 83].rstrip()}..."

    prefix = f"{base_caption}\n👤: "
    caption = prefix + ", ".join(sorted_readers)
    if len(caption) <= READERS_CAPTION_LIMIT:
        return caption

    kept = []
    for index, reader in enumerate(sorted_readers):
        remaining = len(sorted_readers) - index - 1
        suffix = f" и еще {remaining}" if remaining else ""
        candidate = prefix + ", ".join(kept + [reader]) + suffix
        if len(candidate) > READERS_CAPTION_LIMIT:
            break
        kept.append(reader)

    if not kept:
        return f"{prefix}{len(sorted_readers)} человек"

    remaining = len(sorted_readers) - len(kept)
    suffix = f" и еще {remaining}" if remaining else ""
    return prefix + ", ".join(kept) + suffix


def register_tracked_message(tracker, chat_id, message, sender_id, fallback_caption=""):
    messages = _message_list(message)
    display_message = _display_message(messages)
    if not display_message:
        return

    base_caption = _caption_from_message(display_message) or _plain_caption(
        fallback_caption
    )
    now = time.monotonic()
    entry = {
        "chat_id": chat_id,
        "message": message,
        "messages": messages,
        "display_message": display_message,
        "sender_id": sender_id,
        "base_caption": base_caption,
        "readers": set(),
        "created_at": now,
        "next_check_at": now + 1,
        "failures": 0,
        "disabled": False,
    }
    tracker.append(entry)
    print(
        "readers: tracked "
        f"chat_id={chat_id} message_ids={[msg.id for msg in messages]} "
        f"display_id={display_message.id}"
    )


def update_tracked_base_caption(tracker, message, base_caption):
    messages = _message_list(message)
    message_ids = {msg.id for msg in messages}
    if not message_ids:
        return

    plain_caption = _plain_caption(base_caption)
    now = time.monotonic()
    for entry in list(tracker):
        tracked_ids = {msg.id for msg in entry.get("messages", [])}
        if tracked_ids & message_ids:
            entry["base_caption"] = plain_caption
            entry["next_check_at"] = min(entry.get("next_check_at", now), now)


async def _reader_label(client, user_id, cache):
    if user_id in cache:
        return cache[user_id]

    try:
        user = await client.get_entity(user_id)
        if getattr(user, "username", None):
            label = f"@{user.username}"
        else:
            name_parts = [
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
            ]
            label = " ".join(part for part in name_parts if part).strip()
            if not label:
                label = f"id:{user_id}"
    except Exception:
        label = f"id:{user_id}"

    cache[user_id] = label
    return label


async def get_readers(client, chat_id, message_ids, excluded_user_ids, label_cache):
    """Получает список пользователей, прочитавших сообщение."""
    readers = set()
    last_error = None
    for message_id in message_ids:
        if not message_id:
            continue

        try:
            result = await client(
                functions.messages.GetMessageReadParticipantsRequest(
                    peer=chat_id, msg_id=message_id
                )
            )
        except Exception as e:
            last_error = e
            continue

        for read_participant in result:
            user_id = getattr(read_participant, "user_id", None)
            if not user_id or user_id in excluded_user_ids:
                continue
            readers.add(await _reader_label(client, user_id, label_cache))

    if not readers and last_error:
        raise last_error

    return readers


async def update_message_caption(client, entry, readers):
    """Обновляет подпись сообщения списком прочитавших."""
    message = entry.get("display_message") or _display_message(entry.get("messages", []))
    if not message or not getattr(message, "id", None):
        return False

    current_base = _caption_from_message(message)
    if current_base and (
        not entry.get("base_caption")
        or ("⏱️" in entry["base_caption"] and "⏱️" not in current_base)
    ):
        entry["base_caption"] = current_base

    new_caption = _compose_caption(entry.get("base_caption", ""), readers)
    current_caption = getattr(message, "raw_text", "") or ""
    if _normalize_text(new_caption) == _normalize_text(current_caption):
        return False

    updated_message = await message.edit(escape(new_caption), parse_mode="html")
    if updated_message:
        entry["display_message"] = updated_message

    return True


async def _update_entry(client, entry, self_id, label_cache):
    messages = entry.get("messages") or _message_list(entry.get("message"))
    message_ids = [msg.id for msg in messages if getattr(msg, "id", None)]
    if not message_ids:
        entry["disabled"] = True
        return

    excluded_user_ids = {entry.get("sender_id"), self_id}
    excluded_user_ids.discard(None)

    readers = await get_readers(
        client,
        entry["chat_id"],
        message_ids,
        excluded_user_ids,
        label_cache,
    )
    previous_readers = entry.get("readers", set())
    changed = readers != previous_readers

    if changed:
        edited = await update_message_caption(client, entry, readers)
        entry["readers"] = readers
        print(
            "readers: updated "
            f"chat_id={entry['chat_id']} message_ids={message_ids} "
            f"readers={len(readers)} edited={edited}"
        )

    entry["failures"] = 0
    age = time.monotonic() - entry.get("created_at", time.monotonic())
    entry["next_check_at"] = time.monotonic() + _reader_poll_interval(age, changed)


async def update_readers(client, LAST_MESSAGES):
    """Циклически обновляет список прочитавших для отслеживаемых сообщений."""
    me = await client.get_me()
    self_id = getattr(me, "id", None)
    label_cache = {}

    while True:
        try:
            now = time.monotonic()
            for entry in list(LAST_MESSAGES):
                try:
                    if entry.get("disabled"):
                        continue

                    age = now - entry.get("created_at", now)
                    if age > READERS_TRACK_TTL:
                        LAST_MESSAGES.remove(entry)
                        continue

                    if now < entry.get("next_check_at", 0):
                        continue

                    await _update_entry(client, entry, self_id, label_cache)
                except Exception as e:
                    entry["failures"] = entry.get("failures", 0) + 1
                    entry["next_check_at"] = time.monotonic() + min(
                        60, 3 * entry["failures"]
                    )
                    message = str(e)
                    if (
                        "message ID used in the peer was invalid" in message
                        or entry["failures"] >= READERS_MAX_FAILURES
                    ):
                        entry["disabled"] = True
                    if "Message not modified" not in message:
                        print(
                            "Ошибка обработки записи сообщения: "
                            f"{e}; failures={entry['failures']}"
                        )
                    continue
            await asyncio.sleep(READERS_LOOP_SLEEP)
        except Exception as e:
            print(f"Ошибка в цикле update_readers: {e}")
            await asyncio.sleep(READERS_LOOP_SLEEP)
