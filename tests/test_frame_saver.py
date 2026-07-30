"""Focused tests for candidate-frame image persistence failures."""

import importlib
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import ANY, MagicMock, patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


class FrameSaverTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.output_folder = Path(self.temporary_directory.name) / "frames"

    def _frame_saver_with_imwrite(self, return_value: bool):
        fake_cv2 = SimpleNamespace(imwrite=MagicMock(return_value=return_value))
        sys.modules.pop("frame_saver", None)
        with patch.dict(sys.modules, {"cv2": fake_cv2}):
            module = importlib.import_module("frame_saver")
        self.addCleanup(lambda: sys.modules.pop("frame_saver", None))
        return module, fake_cv2.imwrite

    @staticmethod
    def _candidate_frame():
        return SimpleNamespace(frame_number=42, timestamp=1.25, image=object())

    def test_successful_image_write_preserves_the_existing_filename(self):
        saver, imwrite = self._frame_saver_with_imwrite(True)

        saver.save_candidate_frames([self._candidate_frame()], self.output_folder)

        expected_path = self.output_folder / "frame_000042_1.25s.png"
        imwrite.assert_called_once_with(str(expected_path), ANY)

    def test_failed_image_write_reports_the_candidate_frame_path(self):
        saver, _imwrite = self._frame_saver_with_imwrite(False)
        expected_path = self.output_folder / "frame_000042_1.25s.png"

        with self.assertRaisesRegex(
            OSError,
            "Candidate-frame image could not be written",
        ) as error:
            saver.save_candidate_frames([self._candidate_frame()], self.output_folder)

        self.assertIn(str(expected_path), str(error.exception))


if __name__ == "__main__":
    unittest.main()
