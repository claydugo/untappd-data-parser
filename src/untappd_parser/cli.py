import argparse
import json
import sys
from pathlib import Path

from .parser import UntappdParser


def main() -> None:
    parser = argparse.ArgumentParser(description="Process Untappd check-in data")
    parser.add_argument("file", help="JSON file containing Untappd check-in data")
    parser.add_argument(
        "--key",
        choices=["brewery_name", "venue", "beer_type", "photo_url", "bid"],
        default="venue",
        help="Key to use for finding unique entries",
    )
    parser.add_argument(
        "--no-strip-backend", action="store_true", help="Keep backend keys in output"
    )
    parser.add_argument("--no-fancy-dates", action="store_true", help="Keep original date format")
    parser.add_argument("--no-human-keys", action="store_true", help="Keep original key names")
    parser.add_argument(
        "--split-by-visits",
        action="store_true",
        help="Split venue CSV exports by visit count distribution (1, 2-4, 5+)",
    )

    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"Error: File '{args.file}' not found", file=sys.stderr)
        sys.exit(1)

    try:
        untappd = UntappdParser(filename=args.file)
        unique_entries = untappd.get_unique_entries(args.key)

        cleaned_data = untappd.clean_data(
            unique_entries,
            strip_backend=not args.no_strip_backend,
            fancy_dates=not args.no_fancy_dates,
            human_keys=not args.no_human_keys,
        )

        base_filename = f"{Path(args.file).stem}_unique_{args.key}"
        untappd.save_files(cleaned_data, base_filename, split_by_visits=args.split_by_visits)

        stats = untappd.get_stats()
        print(f"Total check-ins: {stats['total_checkins']}")
        print(f"Unique {args.key}s: {len(unique_entries)}")
        print(f"Duplicates: {stats['duplicates']}")

    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"Error processing file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
