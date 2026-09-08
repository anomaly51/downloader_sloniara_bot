import json
import shutil
import subprocess
import tempfile
import unittest
from itertools import pairwise
from pathlib import Path

from PIL import Image

from utils import direct_downloader


class GalleryAssetClassificationTest(unittest.TestCase):
    def test_photos_follow_post_order_instead_of_filename_order(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            expected = []
            for position, name in enumerate(("z", "a", "m"), 1):
                photo = workdir / f"{name}.jpg"
                Image.new("RGB", (32, 32), "red").save(photo)
                photo.with_suffix(".jpg.json").write_text(json.dumps({"num": position}))
                expected.append(photo)
            self.assertEqual(
                direct_downloader._classify_assets(workdir)["photos"], expected
            )

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
                "stream=codec_type,duration,nb_frames,r_frame_rate,avg_frame_rate",
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

    def _photos(self, workdir):
        photos = []
        for index, color in enumerate(("red", "blue", "lime")):
            path = workdir / f"photo-{index}.jpg"
            Image.new("RGB", (160, 120), color).save(path)
            photos.append(path)
        return photos

    def _pixel_at(self, video, timestamp):
        result = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(video),
                "-ss",
                str(timestamp),
                "-frames:v",
                "1",
                "-vf",
                "scale=1:1",
                "-pix_fmt",
                "rgb24",
                "-f",
                "rawvideo",
                "pipe:1",
            ],
            check=True,
            capture_output=True,
        )
        return tuple(result.stdout)

    def test_single_photo_lasts_four_seconds_with_short_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            photo = workdir / "photo.jpg"
            Image.new("RGB", (120, 160), "purple").save(photo)
            audio = workdir / "audio.m4a"
            self._make_audio(audio, 1.6)
            output = workdir / "result.mp4"

            direct_downloader.compose_photo_slideshow([photo], audio, output)

            data = self._probe(output)
            self.assertAlmostEqual(float(data["format"]["duration"]), 4, delta=0.05)
            for stream in data["streams"]:
                self.assertAlmostEqual(float(stream["duration"]), 4, delta=0.05)

    def test_long_audio_is_trimmed_and_photos_change_every_four_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            photos = self._photos(workdir)
            audio = workdir / "audio.m4a"
            self._make_audio(audio, 20)
            output = workdir / "result.mp4"

            result = direct_downloader.compose_photo_slideshow(photos, audio, output)

            self.assertEqual(result, str(output))
            data = self._probe(output)
            self.assertEqual(
                {stream["codec_type"] for stream in data["streams"]},
                {"audio", "video"},
            )
            self.assertAlmostEqual(float(data["format"]["duration"]), 12, delta=0.05)
            for timestamp, channel in (
                (0.1, 0),
                (3.1, 0),
                (4.1, 2),
                (7.1, 2),
                (8.1, 1),
                (11.9, 1),
            ):
                pixel = self._pixel_at(output, timestamp)
                self.assertEqual(len(pixel), 3)
                self.assertGreater(pixel[channel], 220, (timestamp, pixel))
                self.assertTrue(
                    all(value < 30 for i, value in enumerate(pixel) if i != channel)
                )
            video = next(
                stream for stream in data["streams"] if stream["codec_type"] == "video"
            )
            self.assertAlmostEqual(float(video["duration"]), 12, delta=0.05)
            self.assertEqual(int(video["nb_frames"]), 720)
            self.assertEqual(video["r_frame_rate"], "60/1")
            self.assertEqual(video["avg_frame_rate"], "60/1")

            # Halfway through the slide the images are side by side, not blended.
            row = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(output),
                    "-ss",
                    "3.6",
                    "-frames:v",
                    "1",
                    "-vf",
                    "format=rgb24,crop=160:1:0:60",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ],
                check=True,
                capture_output=True,
            ).stdout
            self.assertEqual(len(row), 160 * 3)
            self.assertGreater(row[20 * 3], 220)  # outgoing red photo on the left
            self.assertLess(row[20 * 3 + 2], 30)
            self.assertGreater(row[140 * 3 + 2], 220)  # incoming blue on the right
            self.assertLess(row[140 * 3], 30)

            # Inspect the native frames, without an fps filter hiding timing gaps.
            frames = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_frames",
                        "-show_entries",
                        "frame=best_effort_timestamp_time",
                        "-of",
                        "json",
                        str(output),
                    ]
                )
            )["frames"]
            self.assertEqual(len(frames), 720)
            for index, frame in enumerate(frames):
                self.assertAlmostEqual(
                    float(frame["best_effort_timestamp_time"]), index / 60, places=5
                )

            rows = subprocess.check_output(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(output),
                    "-vf",
                    "trim=start=3.2:end=4,format=rgb24,crop=160:1:0:60",
                    "-fps_mode",
                    "passthrough",
                    "-f",
                    "rawvideo",
                    "pipe:1",
                ]
            )
            self.assertEqual(len(rows), 48 * 160 * 3)
            incoming_widths = []
            for start in range(0, len(rows), 160 * 3):
                row = rows[start : start + 160 * 3]
                incoming_widths.append(
                    sum(row[x + 2] > row[x] for x in range(0, len(row), 3))
                )
            steps = [right - left for left, right in pairwise(incoming_widths)]
            self.assertEqual(incoming_widths, sorted(incoming_widths))
            self.assertGreater(len(set(incoming_widths)), 40)
            self.assertLessEqual(max(steps), 6)
            self.assertLessEqual(max(steps[:3] + steps[-3:]), 2)

    def test_short_audio_does_not_truncate_or_repeat_photos(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            photos = self._photos(workdir)
            audio = workdir / "audio.m4a"
            self._make_audio(audio, 2.4)
            output = workdir / "result.mp4"
            direct_downloader.compose_photo_slideshow(photos, audio, output)
            data = self._probe(output)
            self.assertAlmostEqual(float(data["format"]["duration"]), 12, delta=0.05)
            self.assertGreater(self._pixel_at(output, 11.9)[1], 220)

    def test_photo_only_post_becomes_video_without_audio(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            assets = {
                "photos": self._photos(workdir),
                "videos": [],
                "audio": [],
                "metadata": [{"description": "Album"}],
            }
            content = direct_downloader._build_content(assets, workdir)
            self.assertEqual(content["type"], "video")
            self.assertEqual(content["title"], "Album")
            data = self._probe(content["file"])
            self.assertEqual(
                [stream["codec_type"] for stream in data["streams"]], ["video"]
            )
            self.assertAlmostEqual(float(data["format"]["duration"]), 12, delta=0.05)
            self.assertFalse(list(workdir.glob("slideshow-*")))


if __name__ == "__main__":
    unittest.main()
