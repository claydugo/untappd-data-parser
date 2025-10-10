#!/usr/bin/env python3

import python_minifier
from pathlib import Path


def bundle_python_files():
    src_dir = Path("src/untappd_parser")

    parser_code = (src_dir / "parser.py").read_text()
    web_code = (src_dir / "web.py").read_text()

    # Combine them (parser first, then web)
    # The import in web.py will fail at runtime, so we need to remove it
    combined = f"{parser_code}\n\n{web_code}".replace(
        "from untappd_parser import UntappdParser", ""
    )

    minified = python_minifier.minify(
        combined,
        remove_annotations=True,
        remove_pass=True,
        remove_literal_statements=True,
        combine_imports=True,
        hoist_literals=True,
        rename_locals=True,
        rename_globals=False,
    )

    output_path = Path("src/untappd_parser_bundle.py")
    output_path.write_text(minified)

    original_size = len(combined)
    minified_size = len(minified)
    savings = ((original_size - minified_size) / original_size) * 100

    print(f"✅ Bundle created: {output_path}")
    print(f"   Original size: {original_size:,} bytes")
    print(f"   Minified size: {minified_size:,} bytes")
    print(f"   Savings: {savings:.1f}%")


if __name__ == "__main__":
    bundle_python_files()
