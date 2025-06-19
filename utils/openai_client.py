import os
from openai import OpenAI


def get_openai_client():
    """Инициализирует и возвращает клиент OpenAI."""
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    if not OPENAI_API_KEY:
        raise ValueError("Ошибка: OPENAI_API_KEY не установлен в переменных окружения")

    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENAI_API_KEY,
        default_headers={
            "HTTP-Referer": "YOUR_SITE_URL",
            "X-Title": "YOUR_APP_NAME",
        },
    )
