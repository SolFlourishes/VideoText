import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ground_truth_review import GroundTruthReview, NEEDS_REVIEW, PENDING, VERIFIED


class GroundTruthReviewTests(unittest.TestCase):
    def make(self, root):
        manifest = root / "manifest.json"; ground = root / "ground.json"
        manifest.write_text(json.dumps({"frames":[{"frame_id":"a"},{"frame_id":"b"}]}), encoding="utf-8")
        ground.write_text(json.dumps({"records":[{"frame_id":"a","reference_text":"one","verification_status":PENDING,"reviewer":None,"verification_date":None,"notes":"","unknown":1},{"frame_id":"b","reference_text":"two","verification_status":PENDING,"reviewer":None,"verification_date":None,"notes":""}]}), encoding="utf-8")
        return manifest, ground
    def test_statuses_progress_navigation_and_unknown_data(self):
        with tempfile.TemporaryDirectory() as temp:
            review=GroundTruthReview(*self.make(Path(temp))); review.verify("Reviewer"); self.assertEqual(review.record["verification_status"], VERIFIED); self.assertEqual(review.progress()["verified"],1); self.assertTrue(review.move(1)); review.needs_review(); self.assertEqual(review.record["verification_status"], NEEDS_REVIEW); self.assertFalse(review.move(1)); self.assertEqual(review.data["records"][0]["unknown"],1)
    def test_skip_leaves_pending_and_atomic_save_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, ground=self.make(Path(temp)); review=GroundTruthReview(manifest,ground); self.assertEqual(review.record["verification_status"],PENDING); review.update_text_and_notes("edited","note"); backup=review.save(); self.assertTrue(backup.is_file()); self.assertEqual(json.loads(ground.read_text(encoding="utf-8"))["records"][0]["reference_text"],"edited")
    def test_rejects_malformed_order_or_status(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, ground=self.make(Path(temp)); data=json.loads(ground.read_text()); data["records"][0]["verification_status"]="bad"; ground.write_text(json.dumps(data),encoding="utf-8");
            with self.assertRaises(ValueError): GroundTruthReview(manifest,ground)

if __name__=="__main__": unittest.main()
