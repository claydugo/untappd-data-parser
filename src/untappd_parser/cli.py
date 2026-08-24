import argparse
import json
import sys
import webbrowser
from pathlib import Path

from .pages import BEERMAP_FILENAME, BEERSTATS_FILENAME, render_beermap, render_beerstats
from .parser import UntappdParser

ARTIFACTS = ("map", "stats", "csv", "json")
KEYS = ("brewery_name", "venue", "beer_type", "photo_url", "bid")


def _base_for(key: str) -> str:
    return "venues" if key == "venue" else key


def _count(number: int, singular: str, plural: str) -> str:
    return f"{number:,} {singular if number == 1 else plural}"


def _stale_candidates(base: str, wanted: set[str]) -> set[str]:
    # Only names this run is responsible for. Narrowing with --only must not delete
    # the artifacts it merely declined to rewrite.
    names: set[str] = set()
    if "map" in wanted:
        names.add(BEERMAP_FILENAME)
    if "stats" in wanted:
        names.add(BEERSTATS_FILENAME)
    if "json" in wanted:
        names.add(f"{base}.json")
    if "csv" in wanted:
        names.update(
            {
                f"{base}.csv",
                f"{base}-1-visit.csv",
                f"{base}-2-4-visits.csv",
                f"{base}-5-plus-visits.csv",
            }
        )
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="Process Untappd check-in data")
    parser.add_argument("file", help="JSON file containing Untappd check-in data")
    parser.add_argument(
        "-o",
        "--out-dir",
        default="beer",
        help="Directory to write the exports into (default: beer)",
    )
    parser.add_argument(
        "--only",
        help=f"Comma separated artifacts to write, from: {', '.join(ARTIFACTS)}",
    )
    parser.add_argument(
        "--key",
        choices=KEYS,
        default="venue",
        help="Key to use for finding unique entries",
    )
    parser.add_argument(
        "--strip-backend",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Drop backend-only keys from the CSV and JSON exports",
    )
    parser.add_argument(
        "--fancy-dates",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Rewrite dates as 'January 01, 2024 at 06:00PM'",
    )
    parser.add_argument(
        "--human-keys",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Rewrite keys as 'Venue Name' instead of venue_name",
    )
    parser.add_argument(
        "--split-by-visits",
        action="store_true",
        help="Split venue CSV exports by visit count distribution (1, 2-4, 5+)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the map (or the stats page) in a browser when writing finishes",
    )

    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"Error: File '{args.file}' not found", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        print(f"Error: '{out_dir}' is not a directory", file=sys.stderr)
        sys.exit(1)

    narrowed = args.only is not None
    if narrowed:
        wanted = {item.strip() for item in args.only.split(",") if item.strip()}
        unknown = wanted - set(ARTIFACTS)
        if unknown:
            print(
                f"Error: unknown artifact {', '.join(sorted(unknown))}; "
                f"choose from {', '.join(ARTIFACTS)}",
                file=sys.stderr,
            )
            sys.exit(1)
    else:
        wanted = set(ARTIFACTS)

    split_by_visits = args.split_by_visits
    if split_by_visits and args.key != "venue":
        print(
            f"Warning: --split-by-visits only applies to --key venue; "
            f"writing a single CSV for key '{args.key}'",
            file=sys.stderr,
        )
        split_by_visits = False

    # The map is venue geometry; no other key produces coordinates.
    if "map" in wanted and args.key != "venue":
        if narrowed:
            print(
                f"Warning: the map only applies to --key venue; skipping it for key '{args.key}'",
                file=sys.stderr,
            )
        wanted.discard("map")

    if not wanted:
        print("Error: nothing left to write", file=sys.stderr)
        sys.exit(1)

    try:
        untappd = UntappdParser(filename=args.file)
        unique_entries = untappd.get_unique_entries(args.key)

        out_dir.mkdir(parents=True, exist_ok=True)
        base = _base_for(args.key)
        written: list[tuple[str, str]] = []

        # clean_data mutates entries in place; render the pages from the raw entries first.
        if "map" in wanted:
            page = render_beermap(
                untappd.to_geojson(unique_entries), link_to_stats="stats" in wanted
            )
            (out_dir / BEERMAP_FILENAME).write_text(page, encoding="utf-8")
            written.append((BEERMAP_FILENAME, _count(len(unique_entries), "venue", "venues")))

        if "stats" in wanted:
            stats = untappd.to_dashboard_stats()
            page = render_beerstats(stats, link_to_map="map" in wanted)
            (out_dir / BEERSTATS_FILENAME).write_text(page, encoding="utf-8")
            totals = stats["totals"]
            written.append(
                (
                    BEERSTATS_FILENAME,
                    f"{_count(totals['checkins'], 'check-in', 'check-ins')} · "
                    f"{_count(totals['unique_breweries'], 'brewery', 'breweries')}",
                )
            )

        cleaned_data = untappd.clean_data(
            unique_entries,
            strip_backend=args.strip_backend,
            fancy_dates=args.fancy_dates,
            human_keys=args.human_keys,
            preserve_keys={args.key},
        )

        if "json" in wanted:
            path = out_dir / f"{base}.json"
            path.write_text(
                json.dumps(cleaned_data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            written.append((path.name, _count(len(cleaned_data), "entry", "entries")))

        if "csv" in wanted:
            written.extend(
                (name, _count(rows, "row", "rows"))
                for name, rows in untappd.save_csvs(cleaned_data, out_dir, base, split_by_visits)
            )

        if not written:
            print("The export held no entries, so no files were written", file=sys.stderr)
            return

        # A previous run with other flags can leave files this run did not refresh.
        fresh = {name for name, _ in written}
        candidates = _stale_candidates(base, wanted)
        stale = sorted(
            path
            for path in out_dir.iterdir()
            if path.is_file() and path.name in candidates and path.name not in fresh
        )
        for path in stale:
            path.unlink()

        width = max(len(name) for name, _ in written)
        print(f"Wrote {out_dir}/")
        for name, detail in written:
            print(f"  {name.ljust(width)}  {detail}")
        if stale:
            print(f"Removed {len(stale)} stale: {', '.join(path.name for path in stale)}")

        if args.open:
            opened = BEERMAP_FILENAME if "map" in wanted else BEERSTATS_FILENAME
            target = out_dir / opened
            if target.exists():
                webbrowser.open(target.resolve().as_uri())
            else:
                print("Nothing to open: no page was written", file=sys.stderr)

    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"Error processing file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
