"""Run a manifest-defined preprocessing benchmark; production OCR is unchanged."""
from __future__ import annotations
import argparse, sys
from pathlib import Path
import cv2
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ocr_preprocessing import list_preprocessing_variants
from ocr_preprocessing_experiment import OCRPreprocessingExperimentOptions, run_preprocessing_experiment, write_preprocessing_experiment_report
from preprocessing_benchmark import load_manifest, write_benchmark_summary

def main(argv=None):
    parser=argparse.ArgumentParser(description="Run a verified multi-frame preprocessing benchmark.")
    parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--output-directory",type=Path,required=True); parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args(argv)
    if args.output_directory.exists() and any(args.output_directory.iterdir()) and not args.overwrite: parser.error("output directory is not empty; use --overwrite")
    manifest=load_manifest(args.manifest)
    from ocr_engine import get_ocr_engine
    engine=get_ocr_engine()
    results=[]
    for frame in manifest["frames"]:
        image=cv2.imread(str(frame["image_path"]))
        if image is None: raise RuntimeError(f"Could not read benchmark image: {frame['image_path']}")
        results.append(run_preprocessing_experiment(image,engine.recognize,OCRPreprocessingExperimentOptions(tuple(list_preprocessing_variants()),frame["reference_text"],True),image_name=frame["frame_id"]))
    output=write_preprocessing_experiment_report(results,args.output_directory,source_inputs=[str(frame["image_path"]) for frame in manifest["frames"]],ocr_configuration={"language":"production default","device":"production default"})
    write_benchmark_summary(output/"experiment.json",output)
    print(f"Benchmark reports written to: {output}")
    return 0
if __name__=="__main__": raise SystemExit(main())
