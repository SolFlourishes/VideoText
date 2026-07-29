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


class FixedClock:
    def __call__(self):
        return 0.0


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

    def test_progress_is_throttled_and_final_event_is_emitted(self):
        events = []
        values = [100] * 505

        analyze_video(
            SyntheticVideo([frame(value) for value in values]),
            self.fps,
            progress_callback=lambda current, total: events.append((current, total)),
            total_frames=len(values),
            clock=FixedClock(),
        )

        self.assertEqual(events[0], (1, 505))
        self.assertEqual(events[-1], (505, 505))
        self.assertLess(len(events), 5)

    def test_progress_supports_unknown_totals(self):
        events = []
        analyze_video(
            SyntheticVideo([frame(100)] * 6),
            self.fps,
            progress_callback=lambda current, total: events.append((current, total)),
            total_frames=None,
            clock=FixedClock(),
        )

        self.assertTrue(events)
        self.assertTrue(all(total is None for _, total in events))
        self.assertEqual(events[-1][0], 6)


if __name__ == "__main__":
    unittest.main()
