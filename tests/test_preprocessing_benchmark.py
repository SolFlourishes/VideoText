import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'src'))
from preprocessing_benchmark import load_manifest, decision_rows

class PreprocessingBenchmarkTests(unittest.TestCase):
 def manifest(self,root,frames):
  image=root/'image.png'; image.write_bytes(b'image')
  path=root/'manifest.json'; path.write_text(json.dumps({'schema_version':1,'frames':frames}),encoding='utf-8'); return path
 def frame(self,identifier='frame_1',reference='café'):
  return {'frame_id':identifier,'image':'image.png','selection_reason':'test','layout_categories':['title'],'reference_text':reference}
 def test_manifest_order_relative_path_and_unicode(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); manifest=load_manifest(self.manifest(root,[self.frame('frame_2'),self.frame('frame_1')]))
   self.assertEqual([f['frame_id'] for f in manifest['frames']],['frame_1','frame_2']); self.assertTrue(manifest['frames'][0]['image_path'].is_absolute())
 def test_manifest_rejects_missing_image_reference_duplicate_and_categories(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d); path=self.manifest(root,[self.frame(),self.frame()])
   with self.assertRaisesRegex(ValueError,'Duplicate'): load_manifest(path)
   path.write_text(json.dumps({'schema_version':1,'frames':[self.frame(reference='')]}),encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'Missing reference'): load_manifest(path)
   bad=self.frame();bad['layout_categories']=['bad'];path.write_text(json.dumps({'schema_version':1,'frames':[bad]}),encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'Unsupported'): load_manifest(path)
 def test_decision_rows_counts_medians_worst_and_runtime(self):
  def item(name,cer,wer,comparison,time): return {'variant':name,'status':'success','cer':cer,'wer':wer,'comparison':comparison,'total_seconds':time}
  experiment={'aggregate_results':{'variants':{'original':{'cer':.2,'wer':.3},'threshold':{'cer':.1,'wer':.2}}},'per_image_results':[{'variants':[item('original',.1,.2,'unchanged',2),item('threshold',.05,.1,'improved',3)]},{'variants':[item('original',.3,.4,'unchanged',2),item('threshold',.15,.3,'worsened',3)]}]}
  threshold=next(row for row in decision_rows(experiment) if row['variant']=='threshold')
  self.assertEqual((threshold['frames_improved'],threshold['frames_worsened']), (1,1));self.assertEqual(threshold['median_CER'],.1);self.assertEqual(threshold['worst_WER'],.3);self.assertEqual(threshold['runtime_multiplier'],1.5)
if __name__=='__main__': unittest.main()
