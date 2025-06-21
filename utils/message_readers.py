import asyncio
from telethon import functions


async def get_readers(client, chat_id, message_id, sender_id):
    """Получает список пользователей, прочитавших сообщение."""
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
    """Обновляет подпись сообщения списком прочитавших в формате '👤: @user1, @user2, ...'."""
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
            print(f"Ошибка обновления подписи: {e}")


async def update_readers(client, LAST_MESSAGES):
    """Циклически обновляет список прочитавших для всех сообщений каждые 10 секунд."""
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
                    print(f"Ошибка обработки записи сообщения: {e}")
                    continue
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Ошибка в цикле update_readers: {e}")
            await asyncio.sleep(10)

