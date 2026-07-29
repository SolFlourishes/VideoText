"""Resolve supported VideoText sources into local video files.

The processing pipeline consumes a local path.  This module owns the small
boundary before that pipeline: an existing local file is passed through and an
HTTP(S) URL is streamed into a temporary download workspace.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import shutil
import tempfile
from typing import Callable
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen


class VideoSourceType(Enum):
    """Source types currently supported by VideoText."""

    LOCAL_FILE = "local_file"
    HTTP_URL = "http_url"


class VideoSourceError(ValueError):
    """A source could not be validated, downloaded, or resolved."""


class DownloadCancelledError(VideoSourceError):
    """Downloading stopped before a complete local video was available."""


@dataclass(frozen=True)
class VideoSource:
    """A validated user-selected source before it is resolved locally."""

    value: str
    source_type: VideoSourceType

    @classmethod
    def from_value(cls, value: str) -> "VideoSource":
        """Validate a local file path or an HTTP(S) URL."""

        source_value = value.strip()
        if not source_value:
            raise VideoSourceError("Select a video file or enter an HTTP(S) URL.")

        parsed = urlsplit(source_value)
        # A Windows drive such as C:\\Videos\\lesson.mp4 is parsed as scheme
        # "c" by urlsplit, so only URI-style values are treated as URLs.
        if "://" in source_value:
            scheme = parsed.scheme.lower()
            if scheme not in {"http", "https"}:
                raise VideoSourceError(
                    f"Unsupported video source scheme '{scheme}'. "
                    "Use a local file or an HTTP/HTTPS URL."
                )
            if not parsed.netloc:
                raise VideoSourceError(
                    "HTTP(S) video URLs must include a server name."
                )
            _reject_known_webpage_url(parsed)
            return cls(source_value, VideoSourceType.HTTP_URL)

        local_path = Path(source_value)
        if not local_path.is_file():
            raise VideoSourceError(
                "Video source must be an existing local file. "
                f"Checked path: {local_path}."
            )
        return cls(str(local_path), VideoSourceType.LOCAL_FILE)


@dataclass
class ResolvedVideoSource:
    """A local path ready for the video pipeline and optional temp cleanup."""

    source: VideoSource
    local_path: Path
    temporary_directory: Path | None = None

    def cleanup(self) -> None:
        """Remove the temporary download workspace, if this source owns one."""

        if self.temporary_directory is not None:
            shutil.rmtree(self.temporary_directory, ignore_errors=True)
            self.temporary_directory = None


DownloadProgressCallback = Callable[[int, int | None], None]
CancelCheck = Callable[[], bool]


class DownloadManager:
    """Stream HTTP(S) video sources into an isolated temporary workspace."""

    chunk_size = 64 * 1024

    def __init__(self, temporary_root: Path | None = None) -> None:
        self.temporary_root = temporary_root

    def download(
        self,
        source: VideoSource,
        progress_callback: DownloadProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> ResolvedVideoSource:
        """Download one HTTP(S) source without retaining partial files."""

        if source.source_type is not VideoSourceType.HTTP_URL:
            raise VideoSourceError("Only HTTP(S) sources can be downloaded.")

        temporary_directory = Path(tempfile.mkdtemp(
            prefix="videotext-download-",
            dir=str(self.temporary_root) if self.temporary_root else None,
        ))

        try:
            request = Request(source.value, headers={"User-Agent": "VideoText"})
            with urlopen(request) as response:
                _reject_webpage_content_type(response.headers.get("Content-Type"))
                total = _content_length(response.headers.get("Content-Length"))
                filename = _download_filename(source.value, response)
                output_path = temporary_directory / filename
                downloaded = 0

                if progress_callback is not None:
                    progress_callback(downloaded, total)

                with output_path.open("wb") as output_file:
                    while True:
                        if cancel_check is not None and cancel_check():
                            raise DownloadCancelledError("Video download was cancelled.")

                        chunk = response.read(self.chunk_size)
                        if not chunk:
                            break
                        output_file.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback is not None:
                            progress_callback(downloaded, total)

            if downloaded == 0:
                raise VideoSourceError("Downloaded video is empty.")
            if total is not None and downloaded != total:
                raise VideoSourceError(
                    "Video download ended before the expected size was received."
                )

            _validate_downloaded_video(output_path)

            return ResolvedVideoSource(source, output_path, temporary_directory)
        except VideoSourceError:
            shutil.rmtree(temporary_directory, ignore_errors=True)
            raise
        except Exception as error:
            shutil.rmtree(temporary_directory, ignore_errors=True)
            raise VideoSourceError(f"Could not download video: {error}") from error


def resolve_video_source(
    value: str,
    progress_callback: DownloadProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    download_manager: DownloadManager | None = None,
) -> ResolvedVideoSource:
    """Resolve a supported user source into the local path used by processing."""

    source = VideoSource.from_value(value)
    if source.source_type is VideoSourceType.LOCAL_FILE:
        return ResolvedVideoSource(source, Path(source.value))

    manager = download_manager or DownloadManager()
    return manager.download(source, progress_callback, cancel_check)


def _reject_known_webpage_url(parsed_url) -> None:
    """Reject common video-platform webpage links before any download begins."""

    host = parsed_url.netloc.lower().split(":", maxsplit=1)[0]
    path = parsed_url.path.rstrip("/").lower()
    if host == "youtu.be" or host.endswith(".youtu.be"):
        raise VideoSourceError(
            "This is a YouTube webpage URL, not a direct video-file URL. "
            "YouTube links are not currently supported."
        )
    if (host == "youtube.com" or host.endswith(".youtube.com")) and path == "/watch":
        raise VideoSourceError(
            "This is a YouTube webpage URL, not a direct video-file URL. "
            "YouTube links are not currently supported."
        )


def _reject_webpage_content_type(content_type: str | None) -> None:
    """Reject unmistakable webpage responses without trusting generic types."""

    media_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if media_type in {"text/html", "application/xhtml+xml"}:
        raise VideoSourceError(
            "The URL points to a webpage rather than a directly downloadable "
            "video file. VideoText currently supports direct HTTP or HTTPS "
            "links to video files."
        )


def _validate_downloaded_video(video_path: Path) -> None:
    """Confirm downloaded bytes can be opened as a video before processing."""

    try:
        video, _fps = _open_video_for_validation(video_path)
    except Exception as error:
        raise VideoSourceError(
            "Downloaded content is not a readable video file. VideoText "
            "currently supports direct HTTP or HTTPS links to video files."
        ) from error

    video.release()


def _open_video_for_validation(video_path: Path):
    """Use the existing video-opening mechanism without importing it early."""

    from video_reader import open_video
    return open_video(str(video_path))


def _content_length(value: str | None) -> int | None:
    """Return a usable Content-Length, otherwise preserve unknown size."""

    try:
        length = int(value) if value is not None else 0
    except (TypeError, ValueError):
        return None
    return length if length > 0 else None


def _download_filename(url: str, response) -> str:
    """Choose a safe filename from Content-Disposition or the URL path."""

    disposition = response.headers.get("Content-Disposition", "")
    match = re.search(r"filename\*=UTF-8''([^;]+)|filename=\"?([^\";]+)", disposition, re.I)
    if match:
        candidate = unquote(match.group(1) or match.group(2))
    else:
        response_url = response.geturl() if hasattr(response, "geturl") else url
        candidate = Path(unquote(urlsplit(response_url).path)).name

    safe_name = Path(candidate).name.strip(" .")
    if not safe_name:
        safe_name = "downloaded_video.mp4"
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", safe_name)
    return safe_name if Path(safe_name).suffix else f"{safe_name}.mp4"
