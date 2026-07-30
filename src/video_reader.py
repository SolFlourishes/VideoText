import cv2


def open_video(video_path):
    """
    Opens a video file.

    Returns:
        video: OpenCV VideoCapture object
        fps: Frames per second
    """

    video = cv2.VideoCapture(video_path)

    if not video.isOpened():
        raise ValueError(f"Unable to open video: {video_path}")

    fps = video.get(cv2.CAP_PROP_FPS)

    return video, fps


def get_frame_count(video):
    """Return the reliable total frame count, or ``None`` when unavailable."""
    frame_count = int(video.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    return frame_count if frame_count > 0 else None
