import unittest
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError

from app.schemas.news import NewsCreate
from app.services.news_video_service import (
    canonical_youtube_url,
    download_youtube_video,
    extract_youtube_video_id,
    youtube_thumbnail_url,
    validate_video_upload,
)


class NewsVideoMediaTests(unittest.TestCase):
    def test_image_news_remains_the_backward_compatible_default(self):
        item = NewsCreate(title="Existing photo announcement")

        self.assertEqual(item.media_type, "image")
        self.assertIsNone(item.video_source)
        self.assertIsNone(item.video_url)

    def test_video_news_requires_source_and_url(self):
        with self.assertRaises(ValidationError):
            NewsCreate(title="Missing media", media_type="video")

        valid = NewsCreate(
            title="Uploaded event",
            media_type="video",
            video_source="upload",
            video_url="/uploads/news/videos/event.mp4",
        )
        self.assertEqual(valid.video_source, "upload")

    def test_common_youtube_urls_are_normalized_safely(self):
        for value in (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://youtu.be/dQw4w9WgXcQ?t=3",
            "https://youtube.com/shorts/dQw4w9WgXcQ",
            "dQw4w9WgXcQ",
        ):
            self.assertEqual(extract_youtube_video_id(value), "dQw4w9WgXcQ")

        self.assertIsNone(
            extract_youtube_video_id(
                "https://example.com/watch?v=dQw4w9WgXcQ"
            )
        )
        self.assertEqual(
            canonical_youtube_url("dQw4w9WgXcQ"),
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        )
        self.assertEqual(
            youtube_thumbnail_url("dQw4w9WgXcQ"),
            "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        )

    def test_upload_rejects_unsupported_containers(self):
        self.assertEqual(validate_video_upload("event.MP4", "video/mp4"), ".mp4")
        with self.assertRaises(ValueError):
            validate_video_upload("event.avi", "video/x-msvideo")

    def test_youtube_import_uses_bounded_first_party_download(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "youtube-source.mp4"
            source.write_bytes(b"owned-school-video")
            with (
                patch(
                    "app.services.news_video_service.shutil.which",
                    return_value="/usr/bin/yt-dlp",
                ),
                patch(
                    "app.services.news_video_service._run",
                    return_value=CompletedProcess(
                        args=[],
                        returncode=0,
                        stdout=f"{source}\n",
                        stderr="",
                    ),
                ) as run,
            ):
                result = download_youtube_video(
                    "https://youtu.be/dQw4w9WgXcQ",
                    Path(temp_dir),
                    1024,
                )

            self.assertEqual(result, source)
            command = run.call_args.args[0]
            self.assertIn("--no-playlist", command)
            self.assertIn("--max-filesize", command)
            self.assertEqual(command[-1], canonical_youtube_url("dQw4w9WgXcQ"))


if __name__ == "__main__":
    unittest.main()
