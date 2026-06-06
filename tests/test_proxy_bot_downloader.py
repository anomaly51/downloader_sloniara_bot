import asyncio
import unittest

from utils import proxy_bot_downloader


class FakeButton:
    def __init__(self, text, url=None):
        self.text = text
        self.url = url
        self.data = None


class FakeMessage:
    def __init__(self, buttons):
        self.buttons = buttons
        self.clicked = None

    async def click(self, row_index, button_index):
        self.clicked = (row_index, button_index)
        return "ok"


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


if __name__ == "__main__":
    unittest.main()
