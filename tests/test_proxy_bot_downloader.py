import asyncio
import unittest

from utils import proxy_bot_downloader


class FakeButton:
    def __init__(self, text, url=None):
        self.text = text
        self.url = url
        self.data = None


class FakeMessage:
    def __init__(self, buttons=None, *, file=None, media=None, photo=None, text=""):
        self.buttons = buttons or []
        self.file = file
        self.media = media
        self.photo = photo
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


if __name__ == "__main__":
    unittest.main()
