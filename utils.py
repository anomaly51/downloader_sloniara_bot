import asyncio
import os
import shutil
from telethon import functions

from instagram_handler import download_instagram_video
from tiktok_handler import download_tiktok_video
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
        # Split into prefix and existing readers using partition
        prefix, sep, existing_readers = original_caption.partition("👤:")
        prefix = prefix.rstrip('\n').strip()
        
        new_caption = prefix
        readers_str = ""
        
        if readers:
            # Sort readers and create readers string
            sorted_readers = sorted(readers)
            readers_str = f"\n👤: {', '.join(sorted_readers)}"
            
            # Normalize existing and new readers strings
            existing_normalized = " ".join(existing_readers.strip().split())
            new_normalized = " ".join(readers_str.strip().split())
            
            # Only add if meaningfully different
            if existing_normalized != new_normalized:
                new_caption += readers_str
        
        # Check if we have meaningful changes considering all possible whitespace
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
                    if not message.id:  # Skip if message has no ID
                        continue
                    current_readers = await get_readers(client, chat_id, message.id, sender_id)
                    # Get previous readers from message entry
                    previous_readers = entry.get("readers", set())
                    
                    # Only update if there's an actual change in readers
                    if current_readers != previous_readers:
                        await update_message_caption(client, message, current_readers)
                        # Update stored readers after successful update
                        entry["readers"] = current_readers
                except Exception as e:
                    print(f"Error processing message entry: {e}")
                    continue
            await asyncio.sleep(10)
        except Exception as e:
            print(f"Error in update_readers loop: {e}")
            await asyncio.sleep(10)


def download_video(url):
    if "youtube.com" in url or "youtu.be" in url:
        return download_youtube_video(url)
    elif "tiktok.com" in url:
        return download_tiktok_video(url)
    elif "instagram.com" in url:
        return download_instagram_video(url)
    return None, None, None


async def send_video(client, event, file_path, sender_name, url, video_title):
    caption = (
        f"{sender_name}\n{url}"
        if not video_title
        else f"{sender_name}\n{video_title}\n{url}"
    )
    return await client.send_file(event.chat_id, file_path, caption=caption)


def cleanup(cleanup_path):
    if os.path.isdir(cleanup_path):
        shutil.rmtree(cleanup_path, ignore_errors=True)
    elif os.path.exists(cleanup_path):
        os.remove(cleanup_path)


async def handle_video_link(event, client, LAST_MESSAGES):
    url = event.message.raw_text
    sender = await event.get_sender()
    sender_id = sender.id
    sender_name = f"@{sender.username}" if sender.username else sender.first_name
    status_message = await client.send_message(event.chat_id, "🕰️")
    try:
        file_path, video_title, cleanup_path = download_video(url)
        if not file_path or not os.path.exists(file_path):
            await client.send_message(
                event.chat_id, "Не удалось скачать видео или ссылка не поддерживается."
            )
            return
        message_with_video = await send_video(
            client, event, file_path, sender_name, url, video_title
        )
        cleanup(cleanup_path)
        await event.delete()
        LAST_MESSAGES.append(
            {
                "chat_id": event.chat_id,
                "message": message_with_video,
                "sender_id": sender_id,
                "readers": set()  # Initialize with empty readers set
            }
        )
    except Exception as e:
        await client.send_message(event.chat_id, f"Произошла ошибка: {e}")
    finally:
        await status_message.delete()
