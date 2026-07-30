import unittest, numpy as np
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'src'))
from ocr_preprocessing import apply_preprocessing_variant, list_preprocessing_variants
class Tests(unittest.TestCase):
 def test_variants_dimensions_and_determinism(self):
  image=np.full((10,20,3),128,dtype=np.uint8); original=image.copy()
  for name in list_preprocessing_variants():
   result=apply_preprocessing_variant(image,name); self.assertEqual(result.variant,name); self.assertEqual(result.output_dimensions,(30,15) if name in ('upscale','upscale_sharpen') else (20,10)); np.testing.assert_array_equal(result.image,apply_preprocessing_variant(image,name).image)
  np.testing.assert_array_equal(image,original)
 def test_invalid(self):
  with self.assertRaises(ValueError): apply_preprocessing_variant(np.zeros((2,2),dtype=np.uint8),'bad')
if __name__=='__main__': unittest.main()
