import argparse
import json
import sys
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

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
        "--exclude-untappd-at-home",
        action="store_true",
        help="Exclude the Untappd at Home venue from the map; keep other exports and statistics",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Serve the exports locally and open the map or stats page; Ctrl+C stops the server",
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
        base = _base_for(args.key)
        candidates = _stale_candidates(base, wanted)
        source = Path(args.file).resolve()
        for name in candidates:
            destination = out_dir / name
            if destination.resolve() == source or (
                destination.exists() and destination.samefile(source)
            ):
                raise ValueError(f"Output would replace the input file: {destination}")

        untappd = UntappdParser(filename=args.file)
        unique_entries = (
            untappd.get_unique_entries(args.key) if wanted & {"map", "csv", "json"} else []
        )

        out_dir.mkdir(parents=True, exist_ok=True)
        written: list[tuple[str, str]] = []

        # clean_data mutates entries in place; render the pages from the raw entries first.
        if "map" in wanted:
            geojson = untappd.to_geojson(
                unique_entries, exclude_untappd_at_home=args.exclude_untappd_at_home
            )
            page = render_beermap(geojson, link_to_stats="stats" in wanted)
            (out_dir / BEERMAP_FILENAME).write_text(page, encoding="utf-8")
            written.append((BEERMAP_FILENAME, _count(len(geojson["features"]), "venue", "venues")))

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

        if wanted & {"csv", "json"}:
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

        # A previous run with other flags can leave files this run did not refresh.
        fresh = {name for name, _ in written}
        stale = sorted(
            path
            for path in out_dir.iterdir()
            if path.is_file() and path.name in candidates and path.name not in fresh
        )
        for path in stale:
            path.unlink()

        if not written:
            print("The export held no entries, so no files were written", file=sys.stderr)
            if stale:
                print(f"Removed {len(stale)} stale: {', '.join(path.name for path in stale)}")
            return

        width = max(len(name) for name, _ in written)
        print(f"Wrote {out_dir}/")
        for name, detail in written:
            print(f"  {name.ljust(width)}  {detail}")
        if stale:
            print(f"Removed {len(stale)} stale: {', '.join(path.name for path in stale)}")

        if args.open:
            opened = next(
                (name for name, _ in written if name in (BEERMAP_FILENAME, BEERSTATS_FILENAME)),
                None,
            )
            if opened is None:
                print("Nothing to open: no page was written", file=sys.stderr)
                return
            with ThreadingHTTPServer(
                ("127.0.0.1", 0),
                partial(SimpleHTTPRequestHandler, directory=str(out_dir.resolve())),
            ) as server:
                thread = Thread(target=server.serve_forever, daemon=True)
                thread.start()
                address = f"http://127.0.0.1:{server.server_port}/{opened}"
                print(f"Serving {address}\nPress Ctrl+C to stop.", flush=True)
                try:
                    if not webbrowser.open(address):
                        print("Open the address above in your browser.", file=sys.stderr)
                    thread.join()
                except KeyboardInterrupt:
                    print("\nServer stopped.")
                finally:
                    server.shutdown()
                    thread.join()

    except (ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"Error processing file: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
