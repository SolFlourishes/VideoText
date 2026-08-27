from pathlib import Path
import sys, tempfile, unittest
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from models import CandidateFrame, OCRResult, Presentation, Slide, TextLine, TextParagraph, TextType
from slide_consolidator import consolidate_slides
from translation_application import TranslationApplicationSource, run_translation_job
from translation_contract import TranslationResult, TranslationStatus
from translation_job import TranslationOutputGrouping, TranslationSourceItem
import gui
from translation_settings import (
 OPENAI_TRANSLATION_MODEL, RECOMMENDED_OPENAI_MODEL_LABEL,
 resolve_vetted_openai_model,
)

class FakeProvider:
    provider_id="fake"
    def translate(self, request): return TranslationResult(request, TranslationStatus.SUCCESS, "fake", "translated")

class TranslationApplicationTests(unittest.TestCase):
 def test_translation_consumes_only_promoted_presentation_paragraphs(self):
  weak_line=TextLine("VI M",10,20,10,30,0.65,TextType.BODY)
  protected_line=TextLine("AI",30,40,10,30,0.65,TextType.BODY)
  results=[
   OCRResult("VI M",0.65,np.array([10,10,30,20],dtype=float)),
   OCRResult("AI",0.65,np.array([10,30,30,40],dtype=float)),
  ]
  frame=CandidateFrame(1,0.0,np.zeros((1080,1920,3),dtype=np.uint8),0.0,
   ocr_results=results,text_lines=[weak_line,protected_line],
   text_paragraphs=[TextParagraph("VI M",[weak_line],TextType.BODY),TextParagraph("AI",[protected_line],TextType.BODY)],
   raw_ocr_results=results)
  presentation=Presentation({},consolidate_slides([frame]))
  seen=[]
  class RecordingProvider(FakeProvider):
   def translate(self,request):
    seen.append(request.source_text)
    return super().translate(request)
  source=TranslationApplicationSource(TranslationSourceItem("video-a","Video A","project:a",0),presentation)
  with tempfile.TemporaryDirectory() as directory:
   run_translation_job("job",(source,),"en",("es",),RecordingProvider(),TranslationOutputGrouping.BY_SOURCE,("csv",),Path(directory))
  self.assertEqual(["AI"],seen)
  self.assertEqual("VI M",presentation.slides[0].promotion_records[0].text)

 def test_cloud_model_is_centralized_without_a_bundled_credential(self):
  self.assertEqual("gpt-4.1-mini", OPENAI_TRANSLATION_MODEL)
  self.assertEqual(OPENAI_TRANSLATION_MODEL,resolve_vetted_openai_model(RECOMMENDED_OPENAI_MODEL_LABEL))
  with self.assertRaises(ValueError): resolve_vetted_openai_model("arbitrary-model")
  self.assertNotIn("API_KEY", Path("src/translation_settings.py").read_text(encoding="utf-8"))
  source=Path(gui.__file__).read_text(encoding="utf-8")
  self.assertIn("Uses your OpenAI API key",source); self.assertIn("API charges may apply",source)
 def test_composes_existing_selection_execution_and_exports(self):
  presentation=Presentation({}, [Slide(1,0,1,paragraphs=[TextParagraph("Original",text_type=TextType.BODY)])])
  source=TranslationApplicationSource(TranslationSourceItem("video-a","Video A","project:a",0),presentation)
  with tempfile.TemporaryDirectory() as directory:
   result=run_translation_job("job",(source,),"en",("es","de"),FakeProvider(),TranslationOutputGrouping.BY_SOURCE,("csv","markdown","excel"),Path(directory))
   self.assertEqual(("es","de"),result.job.target_languages); self.assertEqual(2,result.export_result.record_count)
   self.assertEqual(0,result.review_recommended_count)
 def test_failure_continues(self):
  class Provider(FakeProvider):
   def translate(self,request): return TranslationResult(request,TranslationStatus.FAILURE,"fake",error="failed")
  presentation=Presentation({}, [Slide(1,0,1,paragraphs=[TextParagraph("Original",text_type=TextType.BODY)])])
  source=TranslationApplicationSource(TranslationSourceItem("video-a","Video A","project:a",0),presentation)
  with tempfile.TemporaryDirectory() as directory:
   result=run_translation_job("job",(source,),"en",("es",),Provider(),TranslationOutputGrouping.BY_LANGUAGE,("csv",),Path(directory))
  self.assertEqual(1,result.export_result.failure_count)
 def test_completion_text_includes_completed_translation_counts_and_paths(self):
  presentation=Presentation({}, [Slide(1,0,1,paragraphs=[TextParagraph("Original",text_type=TextType.BODY)])])
  source=TranslationApplicationSource(TranslationSourceItem("video-a","Video A","project:a",0),presentation)
  with tempfile.TemporaryDirectory() as directory:
   result=run_translation_job("job",(source,),"en",("es-419",),FakeProvider(),TranslationOutputGrouping.BY_LANGUAGE,("csv",),Path(directory))
   text=gui._format_translation_completion_section(result)
  self.assertIn("Translation\n--------------------", text)
  self.assertIn("Provider: fake",text); self.assertIn("Target languages:\n    Spanish — Latin America", text)
  self.assertIn("Succeeded: 1",text); self.assertIn("Review Recommended: 0",text); self.assertIn("Translation Outputs",text)
  self.assertNotIn("OCR Quality", text)
 def test_completion_text_uses_human_readable_openai_label(self):
  presentation=Presentation({}, [Slide(1,0,1,paragraphs=[TextParagraph("Original",text_type=TextType.BODY)])])
  source=TranslationApplicationSource(TranslationSourceItem("video-a","Video A","project:a",0),presentation)
  class OpenAIProvider(FakeProvider): provider_id="openai"
  with tempfile.TemporaryDirectory() as directory:
   result=run_translation_job("job",(source,),"en",("es-419",),OpenAIProvider(),TranslationOutputGrouping.BY_SOURCE,("csv",),Path(directory))
  self.assertIn("Provider: OpenAI Cloud",gui._format_translation_completion_section(result))
