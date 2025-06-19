import os
import shutil
import re


def cleanup(cleanup_path):
    """Удаляет файл или директорию."""
    if os.path.isdir(cleanup_path):
        shutil.rmtree(cleanup_path, ignore_errors=True)
    elif os.path.exists(cleanup_path):
        os.remove(cleanup_path)


def sanitize_filename(name):
    """Очищает имя файла от недопустимых символов."""
    return re.sub(r'[\\/*?:"<>|]', "", name)
