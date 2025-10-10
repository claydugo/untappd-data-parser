# untappd-data-cleaner
[![License](https://img.shields.io/github/license/mashape/apistatus.svg)](https://github.com/claydugo/untappd-data-cleaner/blob/master/LICENSE)

[Untappd](https://untappd.com/) allows you to download your checkin data in JSON and CSV formats (if you are a [supporter](https://untappd.com/supporter)). This is great, however they do not have an option to download the data of just your 'unique' checkins. This script will take the json file you downloaded from untappd and create both json and csv files with only your last checkins of each beer.

There are also additional parsing options detailed below. I use this to generate the [beer map](https://claydugo.com/beermap/) on my website. So this has become mostly tailored towards that.

## Installation

```bash
pip install -e .
```

## Usage

### Command Line Interface

#### Basic usage - find unique venues (default)
```bash
untappd-parser <UNTAPPD-DATA>.json
```

#### Sort by a different key
Available keys: `brewery_name`, `venue`, `beer_type`, `photo_url`, `bid`

```bash
untappd-parser <UNTAPPD-DATA>.json --key brewery_name
```

#### Split venues by visit frequency (1, 2-4, 5+ visits)
```bash
untappd-parser <UNTAPPD-DATA>.json --split-by-visits
```

This creates 3 separate CSV files:
- `*_1_visit.csv` - venues with exactly 1 visit
- `*_2-4_visits.csv` - venues with 2-4 visits
- `*_5+_visits.csv` - venues with 5 or more visits

##### Additional Flags

- `--no-human-keys` - Keep original snake_case keys (e.g. `venue_name` instead of `Venue Name`)
- `--no-strip-backend` - Keep all keys from the original JSON file
- `--no-fancy-dates` - Keep dates in `YYYY-MM-DD HH:MM:SS` format instead of readable format

### Browser Interface (No installation required!)

Open `untappd.html` in your browser to use the parser without installing Python:

1. **Serve the file**
   ```bash
   python3 -m http.server 8080
   ```
2. **Open in browser**: http://localhost:8080/untappd.html
3. **Drag and drop** your Untappd JSON file
4. **Download** the processed CSVs with visit distribution

## Development

### Building the Minified Python Bundle

The browser interface uses a minified Python bundle (`src/untappd_parser_bundle.py`) generated from the source files. This bundle is automatically rebuilt when you commit changes to the source files via a pre-commit hook.

#### Manual Build

1. **Install dev dependencies**
   ```bash
   pip install -e ".[dev]"
   # or using npm
   npm run build:setup
   ```

2. **Build the bundle**
   ```bash
   npm run build
   # or directly
   python3 build.py
   ```

### Code Quality

Run linters and formatters:

```bash
npm run lint
npm run format
```

## License
MIT
