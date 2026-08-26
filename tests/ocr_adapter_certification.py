"""Reusable assertions for canonical OCR adapter certification tests."""

import numpy as np

from models import OCRResult


def assert_canonical_results(test_case, results) -> None:
    """Verify one adapter response follows VideoText's canonical evidence form."""

    test_case.assertIsInstance(results, list)
    for result in results:
        test_case.assertIsInstance(result, OCRResult)
        test_case.assertIsInstance(result.text, str)
        test_case.assertIsInstance(result.confidence, float)
        test_case.assertTrue(np.isfinite(result.confidence))
        coordinates = np.asarray(result.bounding_box)
        test_case.assertEqual(coordinates.shape, (4,))
        left, top, right, bottom = coordinates
        test_case.assertLessEqual(left, right)
        test_case.assertLessEqual(top, bottom)


def assert_equivalent_results(test_case, first, second) -> None:
    """Verify equivalent canonical evidence without NumPy dataclass equality."""

    test_case.assertEqual(len(first), len(second))
    for expected, actual in zip(first, second):
        test_case.assertEqual(expected.text, actual.text)
        test_case.assertEqual(expected.confidence, actual.confidence)
        np.testing.assert_array_equal(expected.bounding_box, actual.bounding_box)
