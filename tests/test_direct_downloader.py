import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from utils import direct_downloader


class GalleryAssetClassificationTest(unittest.TestCase):
    def test_mp4_with_audio_url_is_classified_as_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            photo = workdir / "photo.jpg"
            audio = workdir / "track.mp4"
            Image.new("RGB", (32, 32), "red").save(photo)
            audio.write_bytes(b"audio-placeholder")
            (workdir / "photo.jpg.json").write_text(
                json.dumps({"description": "caption"}), encoding="utf-8"
            )
            (workdir / "track.mp4.json").write_text(
                json.dumps(
                    {
                        "audio_url": "https://cdn.example/audio.mp4",
                        "audio_title": "Track",
                        "audio_artist": "Artist",
                    }
                ),
                encoding="utf-8",
            )

            assets = direct_downloader._classify_assets(workdir)

            self.assertEqual(assets["photos"], [photo])
            self.assertEqual(assets["audio"], [audio])
            self.assertEqual(assets["videos"], [])
            self.assertEqual(
                direct_downloader._content_title(assets["metadata"]), "caption"
            )

    def test_tiktok_audio_type_is_classified_as_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            audio = workdir / "track.mp4"
            audio.write_bytes(b"audio-placeholder")
            (workdir / "track.mp4.json").write_text(
                json.dumps({"type": "audio", "title": "TikTok caption"}),
                encoding="utf-8",
            )

            assets = direct_downloader._classify_assets(workdir)

            self.assertEqual(assets["audio"], [audio])
            self.assertEqual(assets["videos"], [])
            self.assertEqual(
                direct_downloader._content_title(assets["metadata"]),
                "TikTok caption",
            )


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "ffmpeg and ffprobe are required",
)
class PhotoSlideshowTest(unittest.TestCase):
    def _make_audio(self, path, duration):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency=440:duration={duration}",
                "-c:a",
                "aac",
                str(path),
            ],
            check=True,
            capture_output=True,
        )

    def _probe(self, path):
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        return json.loads(probe.stdout)

    def test_loops_single_photo_for_complete_audio_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            photo = workdir / "photo.jpg"
            Image.new("RGB", (120, 160), "purple").save(photo)
            audio = workdir / "audio.m4a"
            self._make_audio(audio, 1.6)
            output = workdir / "result.mp4"

            direct_downloader.compose_photo_slideshow([photo], audio, output)

            data = self._probe(output)
            self.assertAlmostEqual(float(data["format"]["duration"]), 1.6, delta=0.15)

    def test_builds_carousel_for_complete_audio_duration(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            photos = []
            for index, color in enumerate(("red", "blue", "green")):
                path = workdir / f"photo-{index}.jpg"
                Image.new("RGB", (160, 120), color).save(path)
                photos.append(path)

            audio = workdir / "audio.m4a"
            self._make_audio(audio, 2.4)
            output = workdir / "result.mp4"

            result = direct_downloader.compose_photo_slideshow(photos, audio, output)

            self.assertEqual(result, str(output))
            data = self._probe(output)
            self.assertEqual(
                {stream["codec_type"] for stream in data["streams"]},
                {"audio", "video"},
            )
            self.assertAlmostEqual(float(data["format"]["duration"]), 2.4, delta=0.15)


if __name__ == "__main__":
    unittest.main()
