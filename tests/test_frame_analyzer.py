"""Deterministic regression tests for candidate-frame selection."""

from pathlib import Path
import sys
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from frame_analyzer import analyze_video


class SyntheticVideo:
    """Small in-memory replacement for OpenCV VideoCapture in unit tests."""

    def __init__(self, frames):
        self.frames = frames
        self.index = 0

    def read(self):
        if self.index >= len(self.frames):
            return False, None

        frame = self.frames[self.index]
        self.index += 1
        return True, frame.copy()


def frame(value):
    return np.full((4, 4, 3), value, dtype=np.uint8)


class TerminalStableSlideTests(unittest.TestCase):
    fps = 5

    def analyze(self, values):
        return analyze_video(SyntheticVideo([frame(value) for value in values]), self.fps)

    def test_short_stable_final_slide_is_captured(self):
        # The final slide begins after the last five-second fallback capture
        # and lasts only 18 frames (3.6 seconds).
        candidates = self.analyze([100] * 25 + [104] * 25 + [109] * 4 + [114] * 18)

        self.assertEqual(4, len(candidates))
        self.assertEqual(114, candidates[-1].image[0, 0, 0])

    def test_fade_at_eof_does_not_create_an_extra_slide(self):
        candidates = self.analyze([100] * 25 + [104] * 25 + list(range(109, -1, -5)))

        self.assertEqual(3, len(candidates))
        self.assertEqual(109, candidates[-1].image[0, 0, 0])

    def test_black_terminal_frame_does_not_create_an_extra_slide(self):
        candidates = self.analyze([100] * 25 + [104] * 25 + [109] * 4 + [0] * 18)

        self.assertEqual(3, len(candidates))
        self.assertEqual(109, candidates[-1].image[0, 0, 0])

    def test_rapid_animation_at_eof_does_not_create_an_extra_slide(self):
        animation = [80, 120] * 9
        candidates = self.analyze([100] * 25 + [104] * 25 + [109] * 4 + animation)

        self.assertEqual(3, len(candidates))
        self.assertEqual(109, candidates[-1].image[0, 0, 0])

    def test_single_static_slide_has_one_candidate(self):
        candidates = self.analyze([100] * 72)

        self.assertEqual(1, len(candidates))

    def test_smoke_sequence_has_four_candidate_slides(self):
        candidates = self.analyze([100] * 25 + [104] * 25 + [109] * 4 + [114] * 18)

        self.assertEqual([100, 104, 109, 114], [item.image[0, 0, 0] for item in candidates])


if __name__ == "__main__":
    unittest.main()
