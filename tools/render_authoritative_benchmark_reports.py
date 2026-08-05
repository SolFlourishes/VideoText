"""Render authoritative benchmark reports from existing evidence without OCR."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from authoritative_benchmark_reporting import write_authoritative_reports


def main() -> None:
    """Rewrite the three report formats from the existing authoritative JSON."""

    output_directory = Path("output/task37k_authoritative_benchmark")
    json_path = output_directory / "authoritative_benchmark.json"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    write_authoritative_reports(data, output_directory)
    print(output_directory)


if __name__ == "__main__":
    main()
