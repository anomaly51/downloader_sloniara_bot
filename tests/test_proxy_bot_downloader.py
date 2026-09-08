import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from utils import proxy_bot_downloader


class FakeButton:
    def __init__(self, text, url=None):
        self.text = text
        self.url = url
        self.data = None


class FakeMessage:
    def __init__(
        self,
        buttons=None,
        *,
        file=None,
        media=None,
        photo=None,
        audio=None,
        text="",
        id=None,
    ):
        self.buttons = buttons or []
        self.file = file
        self.media = media
        self.photo = photo
        self.audio = audio
        self.id = id
        self.raw_text = text
        self.clicked = None

    async def click(self, row_index, button_index):
        self.clicked = (row_index, button_index)
        return "ok"


class FakeConversation:
    def __init__(self, responses):
        self.responses = list(responses)
        self.sent_messages = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def send_message(self, text):
        self.sent_messages.append(text)

    async def get_response(self, timeout=None):
        if not self.responses:
            raise asyncio.TimeoutError()

        return self.responses.pop(0)


class FakeClient:
    def __init__(self, conversation):
        self._conversation = conversation

    async def get_entity(self, username):
        return username

    def conversation(self, proxy, timeout=None):
        return self._conversation


class YoutubeQualityButtonTest(unittest.TestCase):
    def test_clicks_preferred_quality_on_media_message(self):
        message = FakeMessage(
            [
                [FakeButton("720p"), FakeButton("480p")],
                [FakeButton("mp3")],
            ]
        )
        message.file = object()

        clicked = asyncio.run(
            proxy_bot_downloader._click_youtube_quality_if_present(
                message, "test-request"
            )
        )

        self.assertTrue(clicked)
        self.assertEqual(message.clicked, (0, 0))

    def test_download_flow_clicks_quality_before_accepting_preview_photo(self):
        preview = FakeMessage(
            [[FakeButton("720p"), FakeButton("480p")], [FakeButton("mp3")]],
            file=object(),
            media=object(),
            photo=object(),
        )
        video = FakeMessage(file=object(), media=object())
        conversation = FakeConversation(
            [
                FakeMessage(text="start"),
                preview,
                video,
            ]
        )
        client = FakeClient(conversation)

        content = asyncio.run(
            proxy_bot_downloader.download_via_proxy_bot(
                client,
                "https://www.youtube.com/watch?v=0xEnVA8KRUI",
                reason="test",
            )
        )

        self.assertEqual(preview.clicked, (0, 0))
        self.assertEqual(content["type"], "telegram_media")
        self.assertEqual(content["source_content_type"], "video")


class ProxyPhotoAlbumTest(unittest.TestCase):
    def test_both_platforms_render_all_photos_with_optional_audio(self):
        for url in (
            "https://www.instagram.com/p/example/",
            "https://www.tiktok.com/@user/photo/123",
        ):
            for has_audio in (True, False):
                with (
                    self.subTest(url=url, audio=has_audio),
                    tempfile.TemporaryDirectory() as directory,
                ):
                    photos = [
                        FakeMessage(file=object(), photo=object(), id=i)
                        for i in range(12)
                    ]
                    audio = FakeMessage(file=object(), audio=object(), id=99)
                    # More than PROXY_MAX_MESSAGES, deliberately arriving out of order.
                    replies = list(reversed(photos))
                    if has_audio:
                        replies.insert(0, audio)
                    conversation = FakeConversation(
                        [FakeMessage(text="start"), *replies]
                    )
                    client = FakeClient(conversation)

                    async def download(message, file):
                        path = Path(file + (".m4a" if message.audio else ".jpg"))
                        path.write_text(str(message.id))
                        return str(path)

                    client.download_media = AsyncMock(side_effect=download)
                    observed = {}

                    def render(paths, audio_path, output, observed=observed):
                        observed["photo_ids"] = [
                            int(Path(path).read_text()) for path in paths
                        ]
                        observed["has_audio"] = bool(audio_path)
                        output.write_bytes(b"video")
                        return str(output)

                    with (
                        patch.object(proxy_bot_downloader, "DOWNLOAD_DIR", directory),
                        patch.object(
                            proxy_bot_downloader,
                            "compose_photo_slideshow",
                            side_effect=render,
                        ),
                    ):
                        content = asyncio.run(
                            proxy_bot_downloader.download_via_proxy_bot(client, url)
                        )
                    self.assertEqual(content["type"], "video")
                    self.assertEqual(observed["photo_ids"], list(range(12)))
                    self.assertEqual(observed["has_audio"], has_audio)
                    self.assertTrue(Path(content["file"]).is_file())

    def test_render_failure_cleans_downloaded_album(self):
        with tempfile.TemporaryDirectory() as directory:
            photo = FakeMessage(file=object(), photo=object())
            client = FakeClient(FakeConversation([FakeMessage(text="start"), photo]))
            client.download_media = AsyncMock(return_value="photo.jpg")
            with (
                patch.object(proxy_bot_downloader, "DOWNLOAD_DIR", directory),
                patch.object(
                    proxy_bot_downloader,
                    "compose_photo_slideshow",
                    side_effect=OSError("render failed"),
                ),
            ):
                content = asyncio.run(
                    proxy_bot_downloader.download_via_proxy_bot(
                        client, "https://www.tiktok.com/@user/photo/123"
                    )
                )
            self.assertIsNone(content)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
