# untappd-data-parser

[![License](https://img.shields.io/github/license/claydugo/untappd-data-parser.svg)](LICENSE)

Convert a JSON export from [Untappd](https://untappd.com/) into a beer map, a statistics dashboard, and CSV or JSON files.
Use the CLI or process the file in your browser.
By default, the CLI groups check-ins by the venue name and coordinates.
Use `--key bid` to keep only the newest check-in for each beer.

I use this to generate the [beer map](https://claydugo.com/beermap/) and [statistics](https://claydugo.com/beerstats/) on my website.
[Untappd Insiders](https://insiders.untappd.com/) includes access to check-in exports.

## Installation

This project uses [Pixi](https://pixi.sh) to manage Python and development tools.
Run this command from the repository root:

```bash
pixi install
```

The package requires Python 3.14 or later and uses only the standard library.
Pixi provides Python 3.14 on Linux (x86-64).

## Usage

### Command Line Interface

#### Basic usage

```bash
pixi run parse export.json
```

This writes everything into `beer/` and prints what it made:

```
Wrote beer/
  beermap.html    1,422 venues
  beerstats.html  4,132 check-ins · 951 breweries
  venues.json    1,422 entries
  venues.csv     1,422 rows
```

Use `-o <dir>` to write somewhere else.
Use `--open` to serve the exports locally and launch the map or stats page.
The terminal prints the local address. Press Ctrl+C to stop the server.

Add `--exclude-untappd-at-home` to exclude the "Untappd at Home" venue from the map.
The option preserves those check-ins in statistics, CSV, and JSON exports.
The browser interface offers the same option before you upload a file.

#### Write only some of it

```bash
pixi run parse export.json --only map
pixi run parse export.json --only csv,json -o exports/
```

The artifacts are `map`, `stats`, `csv`, and `json`. The map needs venue
coordinates, so it is skipped for any `--key` other than `venue`.

A re-run refreshes the artifacts it writes, and clears leftovers from those same
artifacts. Switching `--split-by-visits` off replaces the three bucket CSVs with
`venues.csv` instead of leaving both. Artifacts you did not ask for are left
alone, so `--only map` never touches your CSVs. Anything the tool cannot produce
itself is never removed, and removals are reported.

The CLI rejects output paths that would replace the input file.
An empty CSV export clears stale CSV files for that selection.

#### Split venues by visit frequency (1, 2-4, 5+ visits)

```bash
pixi run parse export.json --split-by-visits
```

This replaces `venues.csv` with a file for each nonempty group:

- `venues-1-visit.csv`
- `venues-2-4-visits.csv`
- `venues-5-plus-visits.csv`

#### Group by a different key

Available keys: `brewery_name`, `venue`, `beer_type`, `photo_url`, `bid`

```bash
pixi run parse export.json --key brewery_name
pixi run parse export.json --key bid
```

Each key other than `venue` keeps the newest check-in for each distinct value.
Statistics always use the full input, regardless of the grouping key.

#### The map page

`beermap.html` contains the venue GeoJSON.
Use `--open` to view it locally, or copy the file to any static host.
Direct `file://` opening does not support the map workers.
The map uses [MapLibre GL](https://maplibre.org) on [OpenFreeMap](https://openfreemap.org) tiles and needs internet access.

Each venue includes its name, location, and check-in details.
Each check-in includes its date, serving type, style, beer identity, beer name, brewery, and listed ABV.
Dates use day precision. Ratings, comments, tagged friends, and exact times stay out of the page.
The map includes clustered bubbles, a heatmap, playback, popups, and summary statistics.
Dark mode follows the system theme.

Open Filters to choose a serving type or search for a style group.
Groups use the Untappd prefix before ` - `. For example, IPA includes American and New England IPAs.
Remove a filter with its chip, even after you close the controls.

On mobile, Filters & view opens a sheet. Tap All dates to show the date fields.
Set From and Through to select an inclusive date range.
Drag either slider handle to adjust the date range.

Playback runs within the selected range and preserves both dates.
All dates resets the date range.
Clear filters restores all dates, styles, and servings. It preserves the view and metric.

Popup details reflect the active filters.
Cluster labels show total check-ins or average ABV, according to the selected metric.
ABV averages use individual check-ins with listed values. The map shows missing ABV in gray and skips it in averages.

Copy the page URL to share the current view.
The link includes dates, beer style, serving type, metric, display mode, and map position.
It also preserves the position of paused playback.

Add `?data=<url>` to load a separate GeoJSON file instead of the embedded copy.
Host the data file on the same origin as the page.
This lets a site update and cache its data separately from the template.
Without this parameter, the page uses its embedded data without a separate fetch.

#### The stats page

`beerstats.html` contains aggregate data, without individual check-in records.
It shows a calendar of check-ins, weekday and hour counts, ABV and IBU histograms, ratings, breweries, countries, and flavors.
The generated page works offline with its embedded data.
Use `?data=<url>` to fetch a separate JSON file instead.

CLI exports link both pages when you select both `map` and `stats`.
The browser ZIP also links both pages. Individual HTML downloads omit the link to the other page.

#### Additional flags

Each of these is on by default and takes a `--no-` form to turn it off.

- `--human-keys` / `--no-human-keys` - `Venue Name` instead of `venue_name`
- `--strip-backend` / `--no-strip-backend` - drop backend-only keys
- `--fancy-dates` / `--no-fancy-dates` - `January 01, 2024 at 06:00PM` instead
  of `2024-01-01 18:00:00`

### Browser interface

Use the [hosted interface](https://claydugo.com/beermap/create.html) without installing Python.
The page downloads [Pyodide](https://pyodide.org) and the package source, then processes your export locally.
It does not upload your check-ins to a server.

Python runs in a worker, so imports and ZIP generation keep the interface responsive.
The interface accepts JSON files up to 50 MiB and groups check-ins by venue.
It splits CSV files by visit frequency by default. The CLI uses one CSV file unless you enable splitting.

To run the interface locally:

```bash
pixi run serve
```

Visit [the local interface](http://localhost:8080/untappd.html), then select or drop your JSON export.
Download all exports as a ZIP, or use the individual download buttons.
Serve the page over HTTP. Direct `file://` opening cannot load the worker and package files.

## Development

Development tasks run through Pixi. See [pixi.toml](pixi.toml) for their definitions.

```bash
pixi run lint
pixi run format
pixi run typecheck
pixi run test
pixi run check
```

`check` runs Ruff, mypy, and the Python tests.
CI also checks formatting and runs browser tests.
For a focused change, select the relevant tests:

```bash
pixi run test tests/test_parser.py -k 'geojson or cli'
```

Run browser checks with the optional Pixi environment:

```bash
pixi run -e browser-tests python -m playwright install chromium
pixi run -e browser-tests test-browser
```

Set `BROWSER_EXECUTABLE` to use an existing Chromium or Chrome executable.
CI installs Chromium and runs these checks with the page security policies enabled.

The browser loads source files directly. Reload after editing; there is no build step.

| File | Role |
| --- | --- |
| `src/untappd_parser/parser.py` | Groups check-ins and prepares exports. |
| `src/untappd_parser/pages.py` | Embeds data in the HTML templates. |
| `src/untappd_parser/web.py` | Processes files and prepares downloads inside the worker. |
| `src/untappd_parser/web.mjs` | Connects browser controls, uploads, and downloads. |
| `untappd.html` | Defines the interface and starts the Pyodide worker. |

The map and dashboard pages live in `src/untappd_parser/templates/`. Each holds a
placeholder token that `pages.py` replaces with the exported JSON. Edit a template
and re-run the CLI to see the change; opening a template on its own shows an error
banner, because the placeholder is not real data.

## License

MIT
