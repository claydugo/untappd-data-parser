# untappd-data-cleaner
[![License](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/claydugo/untappd-data-cleaner/blob/master/LICENSE)

[Untappd](https://untappd.com/) allows you to download your checkin data in JSON and CSV formats (if you are a [supporter](https://untappd.com/supporter)). This is great, however they do not have an option to download the data of just your 'unique' checkins. This script will take the json file you downloaded from untappd and create both json and csv files with only your last checkins of each beer.

There are also additional parsing options detailed below. I use this to generate the [beer map](https://claydugo.com/beermap/) on my website. So this has become mostly tailored towards that.

## Installation

This project uses [pixi](https://pixi.sh) to manage its environment (Python + dev
tooling from conda-forge):

```bash
pixi install
```

Or, for a plain pip install of just the CLI:

```bash
pip install -e .
```

## Usage

### Command Line Interface

#### Basic usage

```bash
untappd-parser <UNTAPPD-DATA>.json
```

This writes everything into `beer/` and prints what it made:

```
Wrote beer/
  beermap.html    1,422 venues · 3,983 check-ins
  beerstats.html  4,132 check-ins · 951 breweries
  venues.json     1,422 entries
  venues.csv      1,422 rows
```

Use `-o <dir>` to write somewhere else.
Use `--open` to serve the exports locally and launch the map or stats page.
The terminal prints the local address. Press Ctrl+C to stop the server.

Add `--exclude-untappd-at-home` to exclude the "Untappd at Home" venue from the map.
The option preserves those check-ins in statistics, CSV, and JSON exports.
The browser interface offers the same option before you upload a file.

#### Write only some of it

```bash
untappd-parser <UNTAPPD-DATA>.json --only map
untappd-parser <UNTAPPD-DATA>.json --only csv,json -o exports/
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
untappd-parser <UNTAPPD-DATA>.json --split-by-visits
```

This replaces `venues.csv` with three files: `venues-1-visit.csv`,
`venues-2-4-visits.csv`, and `venues-5-plus-visits.csv`.

#### Sort by a different key
Available keys: `brewery_name`, `venue`, `beer_type`, `photo_url`, `bid`

```bash
untappd-parser <UNTAPPD-DATA>.json --key brewery_name
```

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

Add `?data=<url>` to load a separate data file instead of the inlined copy. The
parameter is same-origin only, because the page CSP says so. Use it when an
embedding page keeps its own data file, or when you want the browser to cache
the page and the data apart. Without it the page uses the inlined data and makes
no request.

#### The stats page

`beerstats.html` holds aggregate numbers only: check-ins per day, weekday and
hour counts, ABV and IBU histograms, rating distributions, top breweries,
brewery countries, and flavor tags. No single check-in appears in the page. It
renders a check-in calendar, a weekday and hour matrix, histograms, and top
lists. The page loads nothing over the network, so it works offline. It accepts
the same `?data=` override.

When both pages are written they link to each other.

##### Additional Flags

Each of these is on by default and takes a `--no-` form to turn it off.

- `--human-keys` / `--no-human-keys` - `Venue Name` instead of `venue_name`
- `--strip-backend` / `--no-strip-backend` - drop backend-only keys
- `--fancy-dates` / `--no-fancy-dates` - `January 01, 2024 at 06:00PM` instead
  of `2024-01-01 18:00:00`

### Browser Interface (No installation required!)

Open `untappd.html` in your browser to use the parser without installing Python.
[Pyodide](https://pyodide.org) runs the same `untappd_parser` package in the
browser — it fetches the source files directly, so there is no build step or
bundle to maintain.

Python runs in a worker, so imports and ZIP generation keep the interface responsive.

1. **Serve the file**
   ```bash
   pixi run serve   # or: python3 -m http.server 8080
   ```
2. **Open in browser**: http://localhost:8080/untappd.html
3. **Drag and drop** your Untappd JSON file
4. **Download everything as a ZIP**, which holds the same files the CLI writes.
   Individual buttons export one file at a time.

## Development

All dev tasks run through pixi (see `pixi.toml` for the full list):

```bash
pixi run lint        # ruff check
pixi run format      # ruff format
pixi run typecheck   # mypy
pixi run test        # pytest
pixi run check       # lint + typecheck + test (what CI runs)
```

Run browser checks with the optional Pixi environment:

```bash
pixi run -e browser-tests python -m playwright install chromium
pixi run -e browser-tests test-browser
```

Set `BROWSER_EXECUTABLE` to use an existing Chromium or Chrome executable.
CI installs Chromium and runs these checks with the page security policies enabled.

The browser interface (`untappd.html`) loads `src/untappd_parser/` directly via
Pyodide, so editing `parser.py` or `web.py` needs no rebuild — just reload the page.

The map and dashboard pages live in `src/untappd_parser/templates/`. Each holds a
placeholder token that `pages.py` replaces with the exported JSON. Edit a template
and re-run the CLI to see the change; opening a template on its own shows an error
banner, because the placeholder is not real data.

## License
MIT
