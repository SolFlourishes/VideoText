"""Replay one candidate-frame checkpoint through PaddleOCR and RapidOCR.

This evaluation-only runner never registers RapidOCR or invokes normal GUI
processing. It loads the same saved CandidateFrame checkpoint in each fresh
child process, so frame selection is performed exactly once outside this tool.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cache_manager import load_cache
from export_manager import export_all
from full_video_engine_comparison import (
    EngineEvaluationSummary, compare_slide_texts, presentation_text, raw_ocr_evidence, reconstructed_evidence,
    summarize_engine, write_comparison_reports,
)
from models import Presentation
from reading_order import reconstruct_reading_order
from slide_consolidator import consolidate_slides


class _RssSampler:
    def __init__(self) -> None:
        self.process = psutil.Process()
        self.peak = self.process.memory_info().rss
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._sample, daemon=True)

    def _sample(self) -> None:
        while not self.stop.wait(0.01):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()
        self.peak = max(self.peak, self.process.memory_info().rss)


def _engine(name: str):
    if name == "paddle":
        from ocr_engine import PaddleOCREngine
        return PaddleOCREngine(), "paddleocr"
    if name == "rapidocr":
        from rapidocr_engine import RapidOCREngine
        return RapidOCREngine(), "rapidocr"
    raise ValueError(f"Unknown engine: {name}")


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_child(args) -> int:
    try:
        frames = load_cache(args.candidate_frames)
        engine, package = _engine(args.engine)
        started = time.perf_counter()
        with _RssSampler() as sampler:
            initializing = time.perf_counter()
            engine.initialize()
            initialization_seconds = time.perf_counter() - initializing
            ocr_started = time.perf_counter()
            for frame in frames:
                results = engine.recognize(frame.image)
                # Separate lists preserve the same canonical objects, matching production OCR.
                frame.raw_ocr_results = list(results)
                frame.ocr_results = list(results)
            ocr_seconds = time.perf_counter() - ocr_started
            downstream_started = time.perf_counter()
            reconstruct_reading_order(frames)
            slides = consolidate_slides(frames)
            presentation = Presentation(metadata={"video_path": str(args.video_path), "evaluation_engine": args.engine}, slides=slides, statistics={"candidate_frames": len(frames), "slides_detected": len(slides)})
            exported = export_all(presentation, args.engine_output, ["markdown", "csv", "excel"], "sample2", candidate_frames=frames)
            downstream_seconds = time.perf_counter() - downstream_started
            total_seconds = time.perf_counter() - started
        output = Path(args.engine_output)
        _write_json(output / "raw_ocr.json", raw_ocr_evidence(frames))
        _write_json(output / "reconstructed_text.json", reconstructed_evidence(frames, presentation))
        summary = summarize_engine(args.engine, importlib.metadata.version(package), frames, presentation, initialization_seconds, ocr_seconds, downstream_seconds, total_seconds, sampler.peak / (1024 * 1024), exported)
        payload = {"status": "success", "summary": summary.__dict__, "slides": presentation_text(presentation.slides)}
    except Exception as error:
        payload = {"status": "failure", "error": f"{type(error).__name__}: {error}"}
    Path(args.result_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0 if payload["status"] == "success" else 1


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parent(args) -> int:
    root = args.output_directory
    root.mkdir(parents=True, exist_ok=True)
    results = {}
    for engine in ("paddle", "rapidocr"):
        engine_output = root / engine
        engine_output.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / f"{engine}.json"
            command = [sys.executable, str(Path(__file__).resolve()), "--child", "--engine", engine, "--candidate-frames", str(args.candidate_frames), "--video-path", str(args.video_path), "--engine-output", str(engine_output), "--result-path", str(result_path)]
            completed = subprocess.run(command, cwd=Path.cwd(), capture_output=True, text=True)
            if completed.returncode:
                raise RuntimeError(f"{engine} comparison child failed: {completed.stderr.strip() or completed.stdout.strip()}")
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("status") != "success":
                raise RuntimeError(result.get("error", f"{engine} comparison child failed"))
            results[engine] = result
            print(f"{engine}: {result['summary']['candidate_frame_count']} frames, {result['summary']['reconstructed_slide_count']} slides")
    source = {"video_path": str(args.video_path.resolve()), "video_size_bytes": args.video_path.stat().st_size, "video_sha256": _checksum(args.video_path), "candidate_frames_checkpoint": str(args.candidate_frames.resolve()), "candidate_frames_sha256": _checksum(args.candidate_frames)}
    reference_note = "Existing accepted VideoText Sample2 output is a comparison baseline only; it is not presented as human-verified ground truth."
    reports = write_comparison_reports(
        EngineEvaluationSummary(**results["paddle"]["summary"]),
        EngineEvaluationSummary(**results["rapidocr"]["summary"]),
        compare_slide_texts(results["paddle"]["slides"], results["rapidocr"]["slides"]),
        root / "comparison", source, reference_note,
    )
    print("Comparison reports written to:")
    for report in reports:
        print(report)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluation-only full-video PaddleOCR/RapidOCR comparison.")
    parser.add_argument("--video-path", type=Path, required=True)
    parser.add_argument("--candidate-frames", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--engine", choices=("paddle", "rapidocr"))
    parser.add_argument("--engine-output", type=Path)
    parser.add_argument("--result-path", type=Path)
    args = parser.parse_args(argv)
    if args.child:
        return _run_child(args)
    if args.output_directory is None:
        parser.error("--output-directory is required outside child mode")
    return _parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
