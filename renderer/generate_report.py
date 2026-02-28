#!/usr/bin/env python3
"""CLI entry point for generating HTML reports from JSONL files.

Usage:
    python -m renderer.generate_report <jsonl_file> [output_dir]
    python -m renderer.generate_report data/kimwwk/our-pot-app/20260228_120000_test.jsonl reports/
"""

import sys
from pathlib import Path

from .html_generator import HTMLGenerator


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m renderer.generate_report <jsonl_file> [output_dir]")
        sys.exit(1)

    jsonl_path = Path(sys.argv[1])

    if not jsonl_path.exists():
        print(f"Error: File not found: {jsonl_path}")
        sys.exit(1)

    if not jsonl_path.suffix == ".jsonl":
        print(f"Error: File must be a .jsonl file, got: {jsonl_path.suffix}")
        sys.exit(1)

    # Optional output directory (used by GitHub Action)
    output_path = None
    if len(sys.argv) >= 3:
        output_dir = Path(sys.argv[2])
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / jsonl_path.with_suffix(".html").name

    print(f"Generating report for: {jsonl_path}")

    try:
        generator = HTMLGenerator(jsonl_path)
        html_path = generator.generate(output_path)
        print(f"Generated: {html_path}")
    except Exception as e:
        print(f"Error generating report: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
