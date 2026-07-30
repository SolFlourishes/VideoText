"""
frame_saver.py

Saves CandidateFrame images to disk.
"""

from pathlib import Path
import cv2


def save_candidate_frames(candidate_frames, output_folder):
    """
    Save each CandidateFrame image as a PNG.

    Args:
        candidate_frames: List of CandidateFrame objects.
        output_folder: Folder where images will be written.
    """

    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)

    for frame in candidate_frames:

        filename = (
            f"frame_{frame.frame_number:06d}"
            f"_{frame.timestamp:.2f}s.png"
        )

        filepath = output_path / filename

        if not cv2.imwrite(str(filepath), frame.image):
            raise OSError(
                "Candidate-frame image could not be written: "
                f"{filepath}"
            )

    print(f"\nSaved {len(candidate_frames)} images to:")
    print(output_path.resolve())
