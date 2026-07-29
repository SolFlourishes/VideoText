"""Focused tests for local and HTTP(S) video source resolution."""

from io import BytesIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from video_source import (
    DownloadCancelledError,
    DownloadManager,
    VideoSource,
    VideoSourceError,
    VideoSourceType,
    resolve_video_source,
)


class FakeResponse(BytesIO):
    """Minimal urlopen response for deterministic streaming tests."""

    def __init__(self, content: bytes, headers: dict[str, str] | None = None):
        super().__init__(content)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *_arguments):
        self.close()

    def geturl(self):
        return "https://example.test/videos/lesson.mp4"


class VideoSourceTests(unittest.TestCase):
    def test_existing_local_file_is_resolved_without_a_temporary_workspace(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            video = Path(temporary_directory) / "lesson.mp4"
            video.write_bytes(b"video")

            resolved = resolve_video_source(str(video))

            self.assertEqual(resolved.source.source_type, VideoSourceType.LOCAL_FILE)
            self.assertEqual(resolved.local_path, video)
            self.assertIsNone(resolved.temporary_directory)

    def test_http_and_https_urls_are_accepted(self):
        self.assertEqual(
            VideoSource.from_value("http://example.test/video.mp4").source_type,
            VideoSourceType.HTTP_URL,
        )
        self.assertEqual(
            VideoSource.from_value("https://example.test/video.mp4").source_type,
            VideoSourceType.HTTP_URL,
        )

    def test_unsupported_scheme_has_a_clear_error(self):
        with self.assertRaisesRegex(VideoSourceError, "Unsupported video source scheme 'ftp'"):
            VideoSource.from_value("ftp://example.test/video.mp4")

    def test_download_streams_to_a_temporary_workspace_and_cleanup_removes_it(self):
        progress: list[tuple[int, int | None]] = []
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = VideoSource.from_value("https://example.test/video.mp4")
            manager = DownloadManager(root)
            with (
                patch("video_source.urlopen", return_value=FakeResponse(
                    b"video-data", {"Content-Length": "10", "Content-Type": "video/mp4"},
                )),
                patch("video_source._open_video_for_validation", return_value=(MagicMock(), 30)),
            ):
                resolved = manager.download(
                    source,
                    lambda current, total: progress.append((current, total)),
                )

            self.assertEqual(resolved.local_path.read_bytes(), b"video-data")
            self.assertEqual(progress, [(0, 10), (10, 10)])
            workspace = resolved.temporary_directory
            self.assertIsNotNone(workspace)
            resolved.cleanup()
            self.assertFalse(workspace.exists())

    def test_html_response_is_rejected_before_video_validation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = VideoSource.from_value("https://example.test/watch.mp4")
            with (
                patch("video_source.urlopen", return_value=FakeResponse(
                    b"<html>page</html>", {"Content-Type": "text/html"},
                )),
                patch("video_source._open_video_for_validation") as validate,
                self.assertRaisesRegex(VideoSourceError, "webpage rather than a directly downloadable"),
            ):
                DownloadManager(root).download(source)

            validate.assert_not_called()
            self.assertEqual(list(root.iterdir()), [])

    def test_xhtml_response_is_rejected_before_video_validation(self):
        source = VideoSource.from_value("https://example.test/video.mp4")
        with (
            patch("video_source.urlopen", return_value=FakeResponse(
                b"<html />", {"Content-Type": "application/xhtml+xml; charset=utf-8"},
            )),
            self.assertRaisesRegex(VideoSourceError, "webpage rather than a directly downloadable"),
        ):
            DownloadManager().download(source)

    def test_generic_binary_download_is_accepted_when_video_validation_succeeds(self):
        source = VideoSource.from_value("https://example.test/video")
        video = MagicMock()
        with (
            patch("video_source.urlopen", return_value=FakeResponse(
                b"video-data", {"Content-Type": "application/octet-stream"},
            )),
            patch("video_source._open_video_for_validation", return_value=(video, 30)),
        ):
            resolved = DownloadManager().download(source)

        self.assertTrue(resolved.local_path.is_file())
        video.release.assert_called_once()
        resolved.cleanup()

    def test_misleading_mp4_filename_with_html_bytes_is_rejected_and_cleaned_up(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = VideoSource.from_value("https://example.test/page.mp4")
            with (
                patch("video_source.urlopen", return_value=FakeResponse(
                    b"<html>page</html>", {"Content-Type": "video/mp4"},
                )),
                patch("video_source._open_video_for_validation", side_effect=ValueError("not a video")),
                self.assertRaisesRegex(VideoSourceError, "not a readable video file"),
            ):
                DownloadManager(root).download(source)

            self.assertEqual(list(root.iterdir()), [])

    def test_empty_download_is_rejected(self):
        source = VideoSource.from_value("https://example.test/video.mp4")
        with (
            patch("video_source.urlopen", return_value=FakeResponse(b"", {"Content-Type": "video/mp4"})),
            self.assertRaisesRegex(VideoSourceError, "Downloaded video is empty"),
        ):
            DownloadManager().download(source)

    def test_unreadable_binary_download_is_rejected(self):
        source = VideoSource.from_value("https://example.test/video.bin")
        with (
            patch("video_source.urlopen", return_value=FakeResponse(
                b"not-a-video", {"Content-Type": "application/octet-stream"},
            )),
            patch("video_source._open_video_for_validation", side_effect=ValueError("not a video")),
            self.assertRaisesRegex(VideoSourceError, "not a readable video file"),
        ):
            DownloadManager().download(source)

    def test_youtube_watch_url_is_rejected_before_download(self):
        with (
            patch("video_source.urlopen") as urlopen_mock,
            self.assertRaisesRegex(VideoSourceError, "YouTube links are not currently supported"),
        ):
            VideoSource.from_value("https://www.youtube.com/watch?v=example")

        urlopen_mock.assert_not_called()

    def test_youtu_be_url_is_rejected_before_download(self):
        with self.assertRaisesRegex(VideoSourceError, "YouTube links are not currently supported"):
            VideoSource.from_value("https://youtu.be/example")

    def test_cancelled_download_removes_partial_workspace(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = VideoSource.from_value("https://example.test/video.mp4")
            manager = DownloadManager(root)
            manager.chunk_size = 3
            checks = iter((False, True))
            with (
                patch("video_source.urlopen", return_value=FakeResponse(b"video-data")),
                self.assertRaises(DownloadCancelledError),
            ):
                manager.download(source, cancel_check=lambda: next(checks))

            self.assertEqual(list(root.iterdir()), [])

    def test_failed_download_removes_partial_workspace(self):
        class FailingResponse(FakeResponse):
            def __init__(self):
                super().__init__(b"")
                self.calls = 0

            def read(self, _size=-1):
                self.calls += 1
                if self.calls == 1:
                    return b"partial"
                raise OSError("connection lost")

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = VideoSource.from_value("https://example.test/video.mp4")
            with (
                patch("video_source.urlopen", return_value=FailingResponse()),
                self.assertRaisesRegex(VideoSourceError, "Could not download video"),
            ):
                DownloadManager(root).download(source)

            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
