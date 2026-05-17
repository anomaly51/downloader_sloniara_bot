import asyncio
import json
import logging
import os
import re
import time
import traceback
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from telethon.errors import UserAlreadyParticipantError
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest


PROXY_BOT_USERNAME = os.getenv("PROXY_DOWNLOADER_BOT", "TTPapaBot").strip().lstrip("@")
PROXY_TIMEOUT = int(os.getenv("PROXY_DOWNLOADER_TIMEOUT", "120"))
PROXY_START_TIMEOUT = int(os.getenv("PROXY_DOWNLOADER_START_TIMEOUT", "7"))
PROXY_MAX_MESSAGES = int(os.getenv("PROXY_DOWNLOADER_MAX_MESSAGES", "8"))
PROXY_AUTO_JOIN_SPONSORS = (
    os.getenv("PROXY_AUTO_JOIN_SPONSORS", "true").strip().lower()
    in {"1", "true", "yes", "on"}
)
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
DEBUG_LOG_PATH = os.getenv("PROXY_DEBUG_LOG", "./logs/proxy_bot_downloader.log")

_proxy_lock = asyncio.Lock()


def get_proxy_debug_log_path():
    return DEBUG_LOG_PATH


def is_proxy_bot_username(username):
    if not username:
        return False

    return username.strip().lstrip("@").lower() == PROXY_BOT_USERNAME.lower()


def _logger():
    logger = logging.getLogger("proxy_bot_downloader")
    if logger.handlers:
        return logger

    os.makedirs(os.path.dirname(DEBUG_LOG_PATH) or ".", exist_ok=True)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(DEBUG_LOG_PATH, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    return logger


def _log(request_id, event, **data):
    payload = json.dumps(data, ensure_ascii=False, default=str)
    _logger().info("[%s] %s %s", request_id, event, payload)


def _log_error(request_id, event, **data):
    payload = json.dumps(data, ensure_ascii=False, default=str)
    _logger().error("[%s] %s %s", request_id, event, payload)


def _message_buttons(message):
    rows = []
    for row in message.buttons or []:
        button_row = []
        for button in row:
            button_row.append(
                {
                    "text": getattr(button, "text", ""),
                    "url": getattr(button, "url", None),
                    "data": getattr(button, "data", None),
                }
            )
        rows.append(button_row)
    return rows


def _iter_message_buttons(message):
    for row_index, row in enumerate(message.buttons or []):
        for button_index, button in enumerate(row):
            yield row_index, button_index, button


def _message_snapshot(message):
    return {
        "id": getattr(message, "id", None),
        "text": (message.raw_text or "")[:1000],
        "has_media": bool(message.media),
        "has_file": bool(getattr(message, "file", None)),
        "buttons": _message_buttons(message),
    }


def _requires_subscription(message):
    text = (message.raw_text or "").lower()
    markers = [
        "not subscribed",
        "sponsor",
        "subscribe to sponsor",
        "check subscription",
        "подпиш",
        "спонсор",
        "канал",
    ]

    return any(marker in text for marker in markers) and bool(message.buttons)


def _telegram_join_target(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if parsed.scheme == "tg" and parsed.netloc == "join":
        invite = parse_qs(parsed.query).get("invite", [None])[0]
        if invite:
            return {"type": "invite", "value": invite}
        return None

    if host not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        return None

    if path.startswith("+"):
        return {"type": "invite", "value": path[1:].split("/")[0]}

    if path.startswith("joinchat/"):
        invite = path.split("/", 1)[1].split("/")[0]
        if invite:
            return {"type": "invite", "value": invite}
        return None

    username = path.split("/")[0]
    if not username:
        return None

    ignored = {"share", "addstickers", "addemoji", "proxy", "login"}
    if username.lower() in ignored or is_proxy_bot_username(username):
        return None

    return {"type": "public", "value": username}


def _sponsor_join_targets(message):
    targets = []
    seen = set()
    for _, _, button in _iter_message_buttons(message):
        url = getattr(button, "url", None)
        if not url:
            continue

        target = _telegram_join_target(url)
        if not target:
            continue

        key = (target["type"], target["value"])
        if key in seen:
            continue

        seen.add(key)
        targets.append(
            {"target": target, "url": url, "text": getattr(button, "text", "")}
        )

    return targets


async def _join_sponsor_target(client, target, request_id):
    try:
        if target["type"] == "invite":
            await client(ImportChatInviteRequest(target["value"]))
        elif target["type"] == "public":
            await client(JoinChannelRequest(target["value"]))
        else:
            _log_error(request_id, "unknown_join_target", target=target)
            return False

        _log(request_id, "sponsor_join_ok", target=target)
        return True
    except UserAlreadyParticipantError:
        _log(request_id, "sponsor_already_joined", target=target)
        return True
    except Exception as exc:
        if "already" in str(exc).lower() and "participant" in str(exc).lower():
            _log(request_id, "sponsor_already_joined", target=target)
            return True

        _log_error(
            request_id,
            "sponsor_join_failed",
            target=target,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        return False


async def _click_check_subscription(message, request_id):
    for row_index, button_index, button in _iter_message_buttons(message):
        text = (getattr(button, "text", "") or "").lower()
        if "check" not in text and "провер" not in text:
            continue

        try:
            result = await message.click(row_index, button_index)
            _log(
                request_id,
                "check_subscription_clicked",
                button_text=getattr(button, "text", ""),
                result=str(result),
            )
            return True
        except Exception as exc:
            _log_error(
                request_id,
                "check_subscription_click_failed",
                button_text=getattr(button, "text", ""),
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            return False

    _log(request_id, "check_subscription_button_not_found")
    return False


async def _handle_subscription_prompt(client, message, request_id):
    if not _requires_subscription(message):
        return False

    if not PROXY_AUTO_JOIN_SPONSORS:
        _log_error(
            request_id,
            "subscription_required_auto_join_disabled",
            message=_message_snapshot(message),
        )
        return True

    targets = _sponsor_join_targets(message)
    _log(
        request_id,
        "subscription_required_auto_join_start",
        targets=targets,
        message=_message_snapshot(message),
    )

    if not targets:
        _log_error(
            request_id,
            "subscription_required_no_telegram_targets",
            message=_message_snapshot(message),
        )
        return True

    results = []
    for item in targets:
        result = await _join_sponsor_target(client, item["target"], request_id)
        results.append({**item, "joined": result})

    await _click_check_subscription(message, request_id)
    _log(request_id, "subscription_required_auto_join_done", results=results)
    return True


def _is_error_message(message):
    text = (message.raw_text or "").lower()
    markers = [
        "error",
        "failed",
        "can't",
        "cannot",
        "не удалось",
        "ошибка",
        "не найден",
        "недоступ",
    ]

    return any(marker in text for marker in markers)


def _content_type_for_message(message):
    if getattr(message, "voice", None):
        return "voice"
    if getattr(message, "audio", None):
        return "audio"
    if getattr(message, "photo", None):
        return "photos"

    return "video"


async def _proxy_media_content(client, message, request_id, download_media=False):
    content_type = _content_type_for_message(message)

    if not download_media:
        _log(
            request_id,
            "telegram_media_ok",
            message_id=getattr(message, "id", None),
            content_type=content_type,
        )
        return {
            "type": "telegram_media",
            "media": message.media,
            "title": "",
            "source_content_type": content_type,
        }

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    file_path = await client.download_media(message, file=DOWNLOAD_DIR)
    if not file_path:
        _log_error(request_id, "download_media_empty", message=_message_snapshot(message))
        return None

    _log(
        request_id,
        "download_media_ok",
        file_path=file_path,
        content_type=content_type,
    )

    if content_type == "photos":
        return {"type": "photos", "files": [file_path], "title": ""}

    return {"type": content_type, "file": file_path, "title": ""}


async def download_via_proxy_bot(client, url, reason=None, download_media=False):
    request_id = uuid4().hex[:8]
    started_at = time.monotonic()

    async with _proxy_lock:
        _log(
            request_id,
            "start",
            proxy_bot=PROXY_BOT_USERNAME,
            url=url,
            reason=reason,
        )

        try:
            proxy = await client.get_entity(PROXY_BOT_USERNAME)
            async with client.conversation(proxy, timeout=PROXY_TIMEOUT) as conv:
                await conv.send_message("/start")
                _log(request_id, "sent_start")

                try:
                    start_response = await conv.get_response(
                        timeout=PROXY_START_TIMEOUT
                    )
                    _log(
                        request_id,
                        "start_response",
                        message=_message_snapshot(start_response),
                    )
                    if _requires_subscription(start_response):
                        await _handle_subscription_prompt(
                            client, start_response, request_id
                        )
                except asyncio.TimeoutError:
                    _log(request_id, "start_response_timeout")

                await conv.send_message(url)
                _log(request_id, "sent_url")

                for message_index in range(PROXY_MAX_MESSAGES):
                    elapsed = time.monotonic() - started_at
                    remaining = max(1, PROXY_TIMEOUT - int(elapsed))

                    try:
                        response = await conv.get_response(
                            timeout=min(remaining, 30)
                        )
                    except asyncio.TimeoutError:
                        _log_error(
                            request_id,
                            "response_timeout",
                            received_messages=message_index,
                            timeout=PROXY_TIMEOUT,
                        )
                        return None

                    _log(
                        request_id,
                        "response",
                        index=message_index,
                        message=_message_snapshot(response),
                    )

                    if _requires_subscription(response):
                        handled = await _handle_subscription_prompt(
                            client, response, request_id
                        )
                        if handled:
                            await conv.send_message(url)
                            _log(request_id, "resent_url_after_subscription")
                        continue

                    if getattr(response, "file", None):
                        return await _proxy_media_content(
                            client,
                            response,
                            request_id,
                            download_media=download_media,
                        )

                    if _is_error_message(response):
                        _log_error(
                            request_id,
                            "proxy_error_message",
                            message=_message_snapshot(response),
                        )
                        return None

                    if re.search(r"https?://", response.raw_text or ""):
                        _log(
                            request_id,
                            "text_link_response_ignored",
                            message=_message_snapshot(response),
                        )

                _log_error(
                    request_id,
                    "max_messages_without_media",
                    max_messages=PROXY_MAX_MESSAGES,
                )
                return None
        except Exception as exc:
            _log_error(
                request_id,
                "exception",
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            return None
