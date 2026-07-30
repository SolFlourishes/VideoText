"""Run a VideoText accuracy benchmark against JSON or exported CSV input."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from accuracy_benchmark import (  # noqa: E402
    BenchmarkFormatError,
    load_benchmark_dataset,
    load_candidate_dataset,
    report_data,
    run_benchmark,
    write_json_report,
    write_markdown_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare VideoText output to corrected slide text.")
    parser.add_argument("--reference", required=True, type=Path, help="Reference JSON file")
    parser.add_argument("--candidate", required=True, type=Path, help="Candidate JSON or VideoText CSV file")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory for report.json and report.md")
    arguments = parser.parse_args()
    try:
        result = run_benchmark(load_benchmark_dataset(arguments.reference), load_candidate_dataset(arguments.candidate))
    except BenchmarkFormatError as error:
        print(f"Benchmark input error: {error}", file=sys.stderr)
        return 2
    json_path = write_json_report(result, arguments.output_dir / "report.json")
    markdown_path = write_markdown_report(result, arguments.output_dir / "report.md")
    aggregate = report_data(result)["aggregate_metrics"]
    print(f"Benchmark complete: {aggregate['matched_slides']} matched slides")
    print(f"Report JSON: {json_path}")
    print(f"Report Markdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
