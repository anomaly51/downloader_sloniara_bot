import pytest
from unittest.mock import patch, Mock
from tiktok_handler import download_tiktok_video
from youtube_handler import download_youtube_video
from instagram_handler import download_instagram_video

@pytest.fixture
def temp_content_dir(tmp_path):
    content_dir = tmp_path / "content"
    content_dir.mkdir()
    return content_dir

@pytest.mark.asyncio
async def test_tiktok_download(temp_content_dir):
    with patch('pyktok.alt_get_tiktok_json') as mock_get_json, \
         patch('pyktok.save_tiktok') as mock_save:
        mock_get_json.return_value = {
            "__DEFAULT_SCOPE__": {
                "webapp.video-detail": {
                    "shareMeta": {"desc": "Test #description"}
                }
            }
        }
        mock_save.return_value = None
        
        url = "https://www.tiktok.com/@test/video/123"
        result = download_tiktok_video(url)
        assert "content" in result[0]
        assert "Test description" in result[1]

@pytest.mark.asyncio
async def test_youtube_download(temp_content_dir):
    with patch('pytubefix.YouTube') as mock_yt:
        mock_stream = Mock()
        mock_stream.download.return_value = str(temp_content_dir / "video.mp4")
        mock_yt.return_value.streams.get_highest_resolution.return_value = mock_stream
        mock_yt.return_value.title = "Test Video"
        
        url = "https://youtube.com/watch?v=123"
        result = download_youtube_video(url)
        assert "video.mp4" in result[0]
        assert "Test Video" in result[1]

@pytest.mark.asyncio
async def test_instagram_download(temp_content_dir):
    with patch('instaloader.Instaloader') as mock_loader, \
         patch('instaloader.Post') as mock_post:
        mock_post.return_value.shortcode = "abc123"
        mock_loader.return_value.download_post.return_value = None
        
        url = "https://instagram.com/p/abc123/"
        result = download_instagram_video(url)
        assert "abc123" in result[0]
