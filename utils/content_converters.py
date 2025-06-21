import subprocess
import json
import traceback
from .openai_client import get_openai_client
import os


async def get_conversion_action(user_input):
    """Определяет действие конвертации через LLM."""
    openai_client = get_openai_client()
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
            model="deepseek/deepseek-chat",
            messages=[{"role": "system", "content": conversion_prompt}],
            response_format={"type": "json_object"},
        )

        raw_response = response.choices[0].message.content
        print(f"Сырой ответ от LLM: {raw_response}")

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


def convert_video_to_mp3(video_path, output_path=None):
    """Конвертирует видео в MP3."""
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
    """Конвертирует видео в OGG с кодеком Opus для голосового сообщения."""
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
            "-vn",
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
