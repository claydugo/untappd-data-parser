"""Tests for the Untappd export parser.

The sample below mirrors the shape of a real Untappd JSON export: the fields the
parser cares about plus a couple of "backend" keys that `strip_backend` drops.
"""

import csv
import json
from copy import deepcopy
from urllib.request import urlopen

import pytest

from untappd_parser import UntappdParser, VenueLocation
from untappd_parser.cli import main as cli_main
from untappd_parser.pages import render_beermap, render_beerstats


def _inlined_json(page, element_id):
    marker = f'<script type="application/json" id="{element_id}">'
    start = page.index(marker) + len(marker)
    return json.loads(page[start : page.index("</script>", start)])


def _checkin(beer, brewery, venue, lat, lng, created_at, **extra):
    return {
        "beer_name": beer,
        "brewery_name": brewery,
        "beer_type": "IPA",
        "venue_name": venue,
        "venue_lat": lat,
        "venue_lng": lng,
        "created_at": created_at,
        # Backend-only keys that should be stripped by clean_data():
        "checkin_id": 12345,
        "comment": "",
        **extra,
    }


@pytest.fixture
def sample_data():
    # Tavern visited 3 times, Pub once, Cellar 6 times -> exercises all 3 buckets.
    return [
        _checkin("Pliny", "Russian River", "The Tavern", 40.0, -75.0, "2024-01-01 18:00:00"),
        _checkin("Heady", "The Alchemist", "The Tavern", 40.0, -75.0, "2024-02-01 18:00:00"),
        _checkin("Focal", "The Alchemist", "The Tavern", 40.0, -75.0, "2024-03-01 18:00:00"),
        _checkin("Zombie", "Three Floyds", "The Pub", 41.0, -76.0, "2024-01-15 12:00:00"),
        *[
            _checkin("KBS", "Founders", "The Cellar", 42.0, -77.0, f"2024-0{m}-10 20:00:00")
            for m in range(1, 7)
        ],
    ]


@pytest.fixture
def parser(sample_data):
    return UntappdParser(data=sample_data)


def test_requires_data_or_filename():
    with pytest.raises(ValueError, match="Either data or filename"):
        UntappdParser()


def test_loads_from_file(tmp_path, sample_data):
    path = tmp_path / "export.json"
    path.write_text(json.dumps(sample_data), encoding="utf-8")
    parser = UntappdParser(filename=path)
    assert len(parser.data) == len(sample_data)


def test_venue_location_is_frozen_and_hashable():
    venue = VenueLocation(name="The Tavern", latitude=40.0, longitude=-75.0)
    assert venue in {venue}
    with pytest.raises(AttributeError):
        venue.name = "Elsewhere"  # type: ignore[misc]


def test_unique_venues_dedupe_and_count(parser):
    venues = parser.get_unique_entries("venue")
    counts = {v["venue_name"]: v["total_venue_checkins"] for v in venues}
    assert counts == {"The Tavern": 3, "The Pub": 1, "The Cellar": 6}


def test_unique_venues_track_first_and_last_checkin(parser):
    tavern = next(v for v in parser.get_unique_entries("venue") if v["venue_name"] == "The Tavern")
    assert tavern["first_checkin"] == "2024-01-01 18:00:00"
    assert tavern["last_checkin"] == "2024-03-01 18:00:00"


def test_single_visit_has_no_last_checkin(parser):
    pub = next(v for v in parser.get_unique_entries("venue") if v["venue_name"] == "The Pub")
    assert pub["last_checkin"] is None


def test_unique_venues_aggregate_beers_breweries_styles(parser):
    venues = parser.get_unique_entries("venue")
    tavern = next(v for v in venues if v["venue_name"] == "The Tavern")
    assert tavern["unique_beers"] == 3
    assert tavern["unique_breweries"] == 2
    assert tavern["top_styles"] == ["IPA"]
    # The newest check-in at the Tavern is Focal on 2024-03-01.
    assert tavern["last_beer_name"] == "Focal"
    assert tavern["last_beer_brewery"] == "The Alchemist"
    cellar = next(v for v in venues if v["venue_name"] == "The Cellar")
    # Six check-ins of the same beer stay one unique beer.
    assert cellar["unique_beers"] == 1
    assert cellar["unique_breweries"] == 1


def test_unique_venues_average_abv_skips_unlisted():
    tavern_checkin = ["The Tavern", 40.0, -75.0]
    data = [
        _checkin("Pliny", "Russian River", *tavern_checkin, "2024-01-01 18:00:00", beer_abv=8.0),
        _checkin("Heady", "The Alchemist", *tavern_checkin, "2024-02-01 18:00:00", beer_abv=7.0),
        _checkin("Focal", "The Alchemist", *tavern_checkin, "2024-03-01 18:00:00", beer_abv=0),
    ]
    parser = UntappdParser(data=data)
    tavern = parser.get_unique_entries("venue")[0]
    # Zero ABV means unlisted; it must not drag the average down.
    assert tavern["average_abv"] == 7.5
    assert parser.to_geojson([tavern])["features"][0]["properties"]["average_abv"] == 7.5


def test_unique_venues_count_beers_by_bid():
    # Two different beers sharing a name stay two beers.
    data = [
        _checkin("Oktoberfest", "A", "The Tavern", 40.0, -75.0, "2024-01-01 18:00:00", bid=1),
        _checkin("Oktoberfest", "B", "The Tavern", 40.0, -75.0, "2024-02-01 18:00:00", bid=2),
    ]
    tavern = UntappdParser(data=data).get_unique_entries("venue")[0]
    assert tavern["unique_beers"] == 2


def test_aggregates_reject_nonfinite_and_bool_numbers():
    tavern_checkin = ["The Tavern", 40.0, -75.0]
    data = [
        _checkin("Pliny", "RR", *tavern_checkin, "2024-01-01 18:00:00", beer_abv=float("inf")),
        _checkin(
            "Heady",
            "TA",
            *tavern_checkin,
            "2024-02-01 18:00:00",
            beer_abv=float("nan"),
            rating_score=True,
        ),
    ]
    parser = UntappdParser(data=data)
    tavern = parser.get_unique_entries("venue")[0]
    # A bare Infinity token in the GeoJSON would break browser JSON.parse.
    assert "average_abv" not in tavern
    assert [beer["abv"] for beer in tavern["checkin_beers"]] == [None, None]
    json.dumps(parser.to_geojson([tavern]), allow_nan=False)
    stats = parser.to_dashboard_stats()
    assert stats["totals"]["average_abv"] is None
    assert stats["totals"]["average_rating"] is None


def test_unique_venues_keep_sorted_checkin_dates(parser):
    tavern = next(v for v in parser.get_unique_entries("venue") if v["venue_name"] == "The Tavern")
    assert tavern["checkin_dates"] == [
        "2024-01-01 18:00:00",
        "2024-02-01 18:00:00",
        "2024-03-01 18:00:00",
    ]


def test_unique_entries_by_other_key(parser):
    breweries = parser.get_unique_entries("brewery_name")
    assert {b["brewery_name"] for b in breweries} == {
        "Russian River",
        "The Alchemist",
        "Three Floyds",
        "Founders",
    }


def test_clean_data_strips_backend_keys(parser):
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues, fancy_dates=False, human_keys=False)
    assert all("checkin_id" not in entry for entry in cleaned)
    assert all("comment" not in entry for entry in cleaned)


def test_clean_data_humanizes_and_formats(parser):
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues)
    tavern = next(v for v in cleaned if v["Venue Name"] == "The Tavern")
    # Humanized keys + a fancy date string (regression guard for the web preview,
    # which reads exactly "First Checkin"/"Last Checkin").
    assert "First Checkin" in tavern
    assert "Last Checkin" in tavern
    assert tavern["First Checkin"] == "January 01, 2024 at 06:00PM"


def test_visit_distribution_buckets(parser):
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues)
    distribution = parser.get_visit_distribution(cleaned)
    assert [v["Venue Name"] for v in distribution["1_visit"]] == ["The Pub"]
    assert [v["Venue Name"] for v in distribution["2-4_visits"]] == ["The Tavern"]
    assert [v["Venue Name"] for v in distribution["5+_visits"]] == ["The Cellar"]


def test_stats(parser):
    assert parser.get_stats() == {
        "total_checkins": 10,
        "unique_venues": 3,
        "duplicates": 7,
    }


def test_stats_ignore_venueless_checkins(sample_data):
    # A check-in with no venue is not a duplicate visit; it must not inflate the count.
    data = [*sample_data, _checkin("Homebrew", "Me", None, None, None, "2024-06-01 12:00:00")]
    stats = UntappdParser(data=data).get_stats()
    assert stats == {
        "total_checkins": 11,
        "unique_venues": 3,
        "duplicates": 7,
    }


def test_stats_for_other_keys(parser):
    stats = parser.get_stats("brewery_name")
    assert stats == {
        "total_checkins": 10,
        "unique_brewery_names": 4,
        "duplicates": 6,
    }


def test_csv_export_handles_heterogeneous_rows(tmp_path, sample_data):
    # An unparseable created_at leaves raw date keys on one row while other rows
    # get the humanized names; the CSV writer must union the fieldnames.
    data = [*sample_data, _checkin("Mystery", "Unknown", "The Void", 43.0, -78.0, "not-a-date")]
    parser = UntappdParser(data=data)
    cleaned = parser.clean_data(parser.get_unique_entries("venue"))
    parser.save_csvs(cleaned, tmp_path, "venues")

    with (tmp_path / "venues.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4


def test_strip_backend_keys_uses_union_of_all_rows(parser):
    # A backend key missing from the first row but present later must still be stripped.
    data = [
        {"beer_name": "Pliny", "brewery_name": "Russian River"},
        {"beer_name": "Heady", "brewery_name": "The Alchemist", "rating_score": 4.5},
    ]
    cleaned = parser.clean_data(data, fancy_dates=False, human_keys=False)
    assert all("rating_score" not in entry for entry in cleaned)


def test_clean_data_preserves_requested_keys(parser):
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(
        venues, fancy_dates=False, human_keys=False, preserve_keys={"checkin_id"}
    )
    assert all("checkin_id" in entry for entry in cleaned)


def test_split_by_visits_no_longer_depends_on_filename(tmp_path, parser):
    # Splitting used to be gated on "venue" appearing in the filename.
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues)
    parser.save_csvs(cleaned, tmp_path, "venues", split_by_visits=True)
    assert (tmp_path / "venues-1-visit.csv").exists()
    assert (tmp_path / "venues-2-4-visits.csv").exists()
    assert (tmp_path / "venues-5-plus-visits.csv").exists()


def test_split_by_visits_falls_back_to_single_csv_without_visit_counts(tmp_path, parser):
    # Non-venue data matches no visit bucket; a single CSV must be written, not none.
    breweries = parser.get_unique_entries("brewery_name")
    cleaned = parser.clean_data(breweries, preserve_keys={"brewery_name"})
    parser.save_csvs(cleaned, tmp_path, "brewery_name", split_by_visits=True)

    with (tmp_path / "brewery_name.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert not list(tmp_path.glob("*-visit*.csv"))


def test_stats_accept_precomputed_unique_entries(parser):
    unique_entries = parser.get_unique_entries("venue")
    assert parser.get_stats(unique_entries=unique_entries) == parser.get_stats()


def test_to_geojson_builds_point_features(parser):
    venues = parser.get_unique_entries("venue")
    geojson = parser.to_geojson(venues)
    assert geojson["type"] == "FeatureCollection"
    tavern = next(f for f in geojson["features"] if f["properties"]["venue_name"] == "The Tavern")
    # GeoJSON coordinate order is [longitude, latitude].
    assert tavern["geometry"] == {"type": "Point", "coordinates": [-75.0, 40.0]}
    assert tavern["properties"]["total_venue_checkins"] == 3
    # Published dates are day precision; exact times stay private.
    assert tavern["properties"]["first_checkin"] == "2024-01-01"
    assert "checkin_id" not in tavern["properties"]
    assert "venue_lat" not in tavern["properties"]


def test_to_geojson_includes_aggregates_and_dates(parser):
    features = parser.to_geojson(parser.get_unique_entries("venue"))["features"]
    tavern = next(f for f in features if f["properties"]["venue_name"] == "The Tavern")
    assert tavern["properties"]["unique_beers"] == 3
    assert tavern["properties"]["unique_breweries"] == 2
    assert tavern["properties"]["top_styles"] == ["IPA"]
    assert tavern["properties"]["last_beer_name"] == "Focal"
    assert tavern["properties"]["last_beer_brewery"] == "The Alchemist"
    assert tavern["properties"]["checkin_dates"] == ["2024-01-01", "2024-02-01", "2024-03-01"]


def test_to_geojson_keeps_servings_aligned_with_dates():
    data = [
        _checkin(
            "Focal",
            "The Alchemist",
            "The Tavern",
            40.0,
            -75.0,
            "2024-03-01 18:00:00",
            serving_type="Cask",
            beer_type="IPA - New England / Hazy",
        ),
        _checkin(
            "Pliny",
            "Russian River",
            "The Tavern",
            40.0,
            -75.0,
            "2024-01-01 18:00:00",
            serving_type="Draft",
            beer_type="IPA - American",
            bid=42,
            beer_abv="8.0",
        ),
        _checkin(
            "Heady",
            "The Alchemist",
            "The Tavern",
            40.0,
            -75.0,
            "2024-02-01 18:00:00",
            beer_type=None,
        ),
        _checkin("Undated", "The Alchemist", "The Tavern", 40.0, -75.0, None, beer_type="Stout"),
    ]
    features = UntappdParser(data=data).to_geojson(
        UntappdParser(data=data).get_unique_entries("venue")
    )["features"]
    assert features[0]["properties"]["checkin_dates"] == [
        None,
        "2024-01-01",
        "2024-02-01",
        "2024-03-01",
    ]
    assert features[0]["properties"]["checkin_servings"] == ["", "Draft", "", "Cask"]
    assert features[0]["properties"]["checkin_styles"] == [
        "Stout",
        "IPA - American",
        "",
        "IPA - New England / Hazy",
    ]
    assert features[0]["properties"]["checkin_beers"] == [
        {"id": "Undated", "name": "Undated", "brewery": "The Alchemist", "abv": None},
        {"id": 42, "name": "Pliny", "brewery": "Russian River", "abv": 8.0},
        {"id": "Heady", "name": "Heady", "brewery": "The Alchemist", "abv": None},
        {"id": "Focal", "name": "Focal", "brewery": "The Alchemist", "abv": None},
    ]


def test_to_geojson_reports_unmapped_checkins():
    parser = UntappdParser(
        data=[
            _checkin("Pliny", "Russian River", "The Tavern", 40.0, -75.0, None),
            _checkin("Homebrew", "Me", None, None, None, None),
            _checkin("Heady", "The Alchemist", "The Void", float("nan"), -76.0, None),
        ]
    )
    geojson = parser.to_geojson(parser.get_unique_entries("venue"))
    assert geojson["total_checkins"] == 3
    assert len(geojson["features"]) == 1
    assert geojson["features"][0]["properties"]["total_venue_checkins"] == 1


def test_to_geojson_keeps_location_drops_private_fields(parser):
    entry = _checkin(
        "Pliny",
        "Russian River",
        "The Tavern",
        40.0,
        -75.0,
        "2024-01-01 18:00:00",
        venue_city="Philadelphia",
        venue_state="PA",
        venue_country="United States",
        checkin_url="https://untappd.com/user/clay/checkin/1",
        rating_score=4.5,
    )
    properties = parser.to_geojson([entry])["features"][0]["properties"]
    assert properties["venue_city"] == "Philadelphia"
    assert properties["venue_state"] == "PA"
    assert properties["venue_country"] == "United States"
    # Ratings, comments, per-beer fields, and check-in URLs stay out of the
    # published file. Untappd 404s public check-in pages now anyway.
    assert "rating_score" not in properties
    assert "comment" not in properties
    assert "beer_name" not in properties
    assert "brewery_name" not in properties
    assert "checkin_url" not in properties


def test_to_geojson_skips_entries_without_coordinates(parser):
    data = [
        _checkin("Homebrew", "Me", "My House", None, None, "2024-06-01 12:00:00"),
        _checkin("Pliny", "Russian River", "The Tavern", 40.0, -75.0, "2024-01-01 18:00:00"),
    ]
    geojson = parser.to_geojson(data)
    assert [f["properties"]["venue_name"] for f in geojson["features"]] == ["The Tavern"]


def test_to_geojson_omits_null_properties(parser):
    pub = next(v for v in parser.get_unique_entries("venue") if v["venue_name"] == "The Pub")
    feature = parser.to_geojson([pub])["features"][0]
    # A single visit has last_checkin None; the property must be absent, not null.
    assert "last_checkin" not in feature["properties"]


def test_to_geojson_can_exclude_every_venue():
    data = [_checkin("Pliny", "Russian River", "Untappd at Home", 40.0, -75.0, None)]
    parser = UntappdParser(data=data)
    venues = parser.get_unique_entries("venue")
    assert parser.to_geojson(venues, exclude_untappd_at_home=True)["features"] == []
    assert parser.to_geojson(venues)["features"][0]["properties"]["venue_name"] == "Untappd at Home"


def test_to_geojson_coerces_strings_and_skips_non_finite(parser):
    data = [
        _checkin("Pliny", "Russian River", "The Tavern", "40.0", "-75.0", "2024-01-01 18:00:00"),
        _checkin("Heady", "The Alchemist", "The Void", float("nan"), -76.0, "2024-01-02 18:00:00"),
    ]
    features = parser.to_geojson(data)["features"]
    assert [f["properties"]["venue_name"] for f in features] == ["The Tavern"]
    assert features[0]["geometry"]["coordinates"] == [-75.0, 40.0]


def test_cli_beermap_keeps_dates_with_no_strip_backend(tmp_path, sample_data, monkeypatch):
    # clean_data mutates entries in place under --no-strip-backend; the CLI must
    # render the page before cleaning or the check-in dates silently vanish.
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["untappd-parser", str(export), "--only", "map", "--no-strip-backend"]
    )
    cli_main()

    page = (tmp_path / "beer" / "beermap.html").read_text(encoding="utf-8")
    geojson = _inlined_json(page, "venue-data")
    tavern = next(f for f in geojson["features"] if f["properties"]["venue_name"] == "The Tavern")
    assert tavern["properties"]["first_checkin"] == "2024-01-01"
    assert tavern["properties"]["last_checkin"] == "2024-03-01"


def test_dashboard_stats_aggregates():
    data = [
        _checkin(
            "Pliny",
            "Russian River",
            "The Tavern",
            40.0,
            -75.0,
            "2024-01-01 18:00:00",
            beer_abv=8.0,
            beer_ibu=100,
            rating_score=4.5,
            global_weighted_rating_score=4.2,
            brewery_country="United States",
            flavor_profiles="juicy, piney",
            bid=1,
        ),
        _checkin(
            "Heady",
            "The Alchemist",
            "The Tavern",
            40.0,
            -75.0,
            "2024-01-01 20:00:00",
            beer_abv=8.0,
            beer_ibu=75,
            rating_score="",
            global_weighted_rating_score=4.4,
            brewery_country="United States",
            flavor_profiles="juicy",
            bid=2,
        ),
    ]
    stats = UntappdParser(data=data).to_dashboard_stats()
    assert stats["totals"]["checkins"] == 2
    assert stats["totals"]["unique_beers"] == 2
    assert stats["totals"]["unique_venues"] == 1
    assert stats["totals"]["average_abv"] == 8.0
    # An empty-string rating is unrated, not zero.
    assert stats["totals"]["average_rating"] == 4.5
    assert stats["totals"]["flavor_tagged_checkins"] == 2
    assert stats["checkins_per_day"] == {"2024-01-01": 2}
    # 2024-01-01 is a Monday.
    assert stats["weekday_hour"][0][18] == 1
    assert stats["weekday_hour"][0][20] == 1
    assert stats["abv_histogram"]["counts"][16] == 2
    assert stats["ibu_histogram"]["counts"][10] == 1
    assert stats["ibu_histogram"]["counts"][7] == 1
    assert stats["rating_histograms"]["mine"][18] == 1
    assert sum(stats["rating_histograms"]["mine"]) == 1
    assert sum(stats["rating_histograms"]["global"]) == 2
    assert stats["brewery_countries"] == [{"country": "United States", "checkins": 2}]
    assert stats["flavor_profiles"][0] == {"flavor": "juicy", "checkins": 2}
    assert len(stats["top_breweries"]) == 2


def test_dashboard_stats_empty_data():
    stats = UntappdParser(data=[]).to_dashboard_stats()
    assert stats["totals"]["checkins"] == 0
    assert stats["totals"]["first_day"] is None
    assert stats["totals"]["average_abv"] is None
    assert stats["top_breweries"] == []


def test_dashboard_stats_counts_venues_by_name_and_location():
    data = [
        {"venue_name": "Tavern", "venue_lat": 40, "venue_lng": -75},
        {"venue_name": "Tavern", "venue_lat": 40.0, "venue_lng": -75.0},
        {"venue_name": "Tavern", "venue_lat": 41, "venue_lng": -75},
        {"venue_name": "Pub", "venue_lat": 40, "venue_lng": -75},
        {"venue_name": "Zero", "venue_lat": 0, "venue_lng": 0},
        {"venue_name": "", "venue_lat": 0, "venue_lng": 0},
        {"venue_name": None, "venue_lat": 40, "venue_lng": -75},
        {"venue_name": "Tavern", "venue_lat": None, "venue_lng": -75},
        {"venue_name": "Tavern", "venue_lat": 40, "venue_lng": None},
    ]
    stats = UntappdParser(data=data).to_dashboard_stats()
    assert stats["totals"]["unique_venues"] == 5
    assert stats["totals"]["checkins"] == 9


def test_csv_serializes_list_values(tmp_path, parser):
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues, strip_backend=False, fancy_dates=False, human_keys=False)
    parser.save_csvs(cleaned, tmp_path, "venues")

    with (tmp_path / "venues.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    tavern = next(row for row in rows if row["venue_name"] == "The Tavern")
    assert tavern["top_styles"] == "IPA"
    assert tavern["checkin_dates"].startswith("2024-01-01 18:00:00; ")


def test_cli_beerstats_writes_page(tmp_path, sample_data, monkeypatch):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export), "--only", "stats"])
    cli_main()

    page = (tmp_path / "beer" / "beerstats.html").read_text(encoding="utf-8")
    stats = _inlined_json(page, "stats-data")
    assert stats["totals"]["checkins"] == 10
    assert stats["totals"]["unique_venues"] == 3


@pytest.mark.parametrize("exclude_untappd_at_home", [False, True])
def test_cli_excludes_untappd_at_home_only_from_map(
    tmp_path, sample_data, monkeypatch, capsys, exclude_untappd_at_home
):
    data = [
        *sample_data,
        _checkin("Pliny", "Russian River", "Untappd at Home", 40.0, -75.0, None),
        _checkin("Heady", "The Alchemist", "Untappd at Homebrew", 40.0, -75.0, None),
    ]
    export = tmp_path / "export.json"
    export.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    arguments = ["untappd-parser", str(export)]
    if exclude_untappd_at_home:
        arguments.append("--exclude-untappd-at-home")
    monkeypatch.setattr("sys.argv", arguments)
    cli_main()

    geojson = _inlined_json((tmp_path / "beer" / "beermap.html").read_text(), "venue-data")
    names = {feature["properties"]["venue_name"] for feature in geojson["features"]}
    assert ("Untappd at Home" in names) is not exclude_untappd_at_home
    assert "Untappd at Homebrew" in names
    assert "The Tavern" in names
    assert f"{len(names)} venues" in capsys.readouterr().out
    stats = _inlined_json((tmp_path / "beer" / "beerstats.html").read_text(), "stats-data")
    assert stats["totals"]["checkins"] == 12
    assert stats["totals"]["unique_venues"] == 5
    exported = json.loads((tmp_path / "beer" / "venues.json").read_text())
    assert any(entry["Venue Name"] == "Untappd at Home" for entry in exported)
    with (tmp_path / "beer" / "venues.csv").open() as file:
        assert any(entry["Venue Name"] == "Untappd at Home" for entry in csv.DictReader(file))
    assert json.loads(export.read_text()) == data


def test_cli_writes_everything_into_one_directory(tmp_path, sample_data, monkeypatch):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export)])
    cli_main()

    assert sorted(p.name for p in (tmp_path / "beer").iterdir()) == [
        "beermap.html",
        "beerstats.html",
        "venues.csv",
        "venues.json",
    ]


def test_cli_out_dir_and_only(tmp_path, sample_data, monkeypatch):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", ["untappd-parser", str(export), "-o", "site", "--only", "map,csv"]
    )
    cli_main()

    assert sorted(p.name for p in (tmp_path / "site").iterdir()) == [
        "beermap.html",
        "venues.csv",
    ]


@pytest.mark.parametrize(
    ("artifacts", "page_name"),
    [("map,stats", "beermap.html"), ("stats", "beerstats.html")],
)
def test_cli_open_serves_generated_pages(
    tmp_path, sample_data, monkeypatch, capsys, artifacts, page_name
):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["untappd-parser", str(export), "--only", artifacts, "-o", "my exports", "--open"],
    )
    addresses = []

    def open_browser(address):
        addresses.append(address)
        assert address.startswith("http://127.0.0.1:")
        assert address.endswith(f"/{page_name}")
        with urlopen(address, timeout=5) as response:  # noqa: S310
            page = response.read().decode()
        if page_name == "beermap.html":
            assert _inlined_json(page, "venue-data")["total_checkins"] == 10
            with urlopen(address.replace("beermap.html", "beerstats.html"), timeout=5) as response:  # noqa: S310
                assert (
                    _inlined_json(response.read().decode(), "stats-data")["totals"]["checkins"]
                    == 10
                )
        else:
            assert _inlined_json(page, "stats-data")["totals"]["checkins"] == 10
        raise KeyboardInterrupt

    monkeypatch.setattr("untappd_parser.cli.webbrowser.open", open_browser)
    cli_main()
    assert len(addresses) == 1
    assert "Server stopped." in capsys.readouterr().out


def test_cli_open_does_not_open_stale_pages(tmp_path, sample_data, monkeypatch, capsys):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "beer").mkdir()
    (tmp_path / "beer" / "beerstats.html").write_text("stale", encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export), "--only", "csv", "--open"])
    monkeypatch.setattr("untappd_parser.cli.webbrowser.open", lambda address: pytest.fail(address))
    cli_main()
    assert "Nothing to open: no page was written" in capsys.readouterr().err


def test_cli_clears_its_own_stale_files(tmp_path, sample_data, monkeypatch):
    # A dir reused with other flags must not keep last run's data as if it were fresh.
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(
        "sys.argv", ["untappd-parser", str(export), "--only", "csv", "--split-by-visits"]
    )
    cli_main()
    assert (tmp_path / "beer" / "venues-1-visit.csv").exists()

    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export), "--only", "csv"])
    cli_main()
    assert sorted(p.name for p in (tmp_path / "beer").iterdir()) == ["venues.csv"]


def test_cli_only_does_not_delete_the_artifacts_it_skipped(tmp_path, sample_data, monkeypatch):
    # --only narrows what gets written. It must not clear the rest of the directory.
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export)])
    cli_main()
    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export), "--only", "map"])
    cli_main()

    assert sorted(p.name for p in (tmp_path / "beer").iterdir()) == [
        "beermap.html",
        "beerstats.html",
        "venues.csv",
        "venues.json",
    ]


def test_cli_leaves_unrelated_files_alone(tmp_path, sample_data, monkeypatch):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "beer").mkdir()
    keeper = tmp_path / "beer" / "notes.txt"
    keeper.write_text("mine", encoding="utf-8")

    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export), "--only", "csv"])
    cli_main()
    assert keeper.read_text(encoding="utf-8") == "mine"


def test_cli_rejects_an_unknown_artifact(tmp_path, sample_data, monkeypatch, capsys):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export), "--only", "map,bogus"])
    with pytest.raises(SystemExit):
        cli_main()
    assert "unknown artifact bogus" in capsys.readouterr().err


def test_cli_rejects_an_out_dir_that_is_a_file(tmp_path, sample_data, monkeypatch, capsys):
    export = tmp_path / "export.json"
    export.write_text(json.dumps(sample_data), encoding="utf-8")
    (tmp_path / "blocker").write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["untappd-parser", str(export), "-o", "blocker"])
    with pytest.raises(SystemExit):
        cli_main()
    assert "not a directory" in capsys.readouterr().err


def test_pages_link_to_each_other_only_when_both_are_written(parser):
    geojson = parser.to_geojson(parser.get_unique_entries("venue"))
    assert 'href="beerstats.html"' in render_beermap(geojson, link_to_stats=True)
    assert 'href="beerstats.html"' not in render_beermap(geojson)
    stats = parser.to_dashboard_stats()
    assert 'href="beermap.html"' in render_beerstats(stats, link_to_map=True)
    assert 'href="beermap.html"' not in render_beerstats(stats)


def test_rendered_pages_carry_no_placeholder(parser):
    beermap = render_beermap(parser.to_geojson(parser.get_unique_entries("venue")))
    beerstats = render_beerstats(parser.to_dashboard_stats())
    assert "__UNTAPPD_VENUE_DATA__" not in beermap
    assert "__UNTAPPD_STATS_DATA__" not in beerstats
    assert "__UNTAPPD_SIBLING_LINK__" not in beermap
    assert "__UNTAPPD_SIBLING_LINK__" not in beerstats
    assert len(_inlined_json(beermap, "venue-data")["features"]) == 3
    assert _inlined_json(beerstats, "stats-data")["totals"]["unique_venues"] == 3


def test_rendered_pages_keep_the_data_override(parser):
    # ?data= lets an embedding page swap in its own copy; it is easy to drop by accident.
    beermap = render_beermap(parser.to_geojson(parser.get_unique_entries("venue")))
    beerstats = render_beerstats(parser.to_dashboard_stats())
    for page in (beermap, beerstats):
        assert 'new URLSearchParams(location.search).get("data")' in page


def test_render_beermap_escapes_markup_in_venue_names():
    # A venue name holding a closing script tag would end the data block early.
    data = [
        _checkin("Pliny", "R&R", "</script><script>alert(1)</script>", 40.0, -75.0, None),
    ]
    parser = UntappdParser(data=data)
    page = render_beermap(parser.to_geojson(parser.get_unique_entries("venue")))

    assert "</script><script>alert(1)" not in page
    properties = _inlined_json(page, "venue-data")["features"][0]["properties"]
    assert properties["venue_name"] == "</script><script>alert(1)</script>"


def test_save_csvs_reports_what_it_wrote(tmp_path, parser):
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues)
    written = parser.save_csvs(cleaned, tmp_path, "venues", split_by_visits=True)

    assert written == [
        ("venues-1-visit.csv", 1),
        ("venues-2-4-visits.csv", 1),
        ("venues-5-plus-visits.csv", 1),
    ]
    with (tmp_path / "venues-5-plus-visits.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [row["Venue Name"] for row in rows] == ["The Cellar"]


@pytest.mark.parametrize("strip_backend", [False, True])
@pytest.mark.parametrize("human_keys", [False, True])
def test_clean_data_preserves_input_and_respects_key_format(parser, strip_backend, human_keys):
    venues = parser.get_unique_entries("venue")
    original = deepcopy(venues)
    cleaned = parser.clean_data(venues, strip_backend=strip_backend, human_keys=human_keys)
    assert venues == original
    assert cleaned[0]["First Checkin" if human_keys else "first_checkin"] == (
        "January 01, 2024 at 06:00PM"
    )
    assert ("First Checkin" in cleaned[0]) is human_keys
    assert parser.clean_data(venues, strip_backend=strip_backend, human_keys=human_keys) == cleaned


def test_unique_entries_keep_newest_checkin_in_any_order():
    newest = {"bid": 1, "beer_name": "Newest", "created_at": "2025-01-01 12:00:00"}
    older = {"bid": 1, "beer_name": "Older", "created_at": "2024-01-01 12:00:00"}
    undated = {"bid": 1, "beer_name": "Undated", "created_at": None}
    for data in ([newest, older, undated], [undated, older, newest]):
        assert UntappdParser(data=data).get_unique_entries("bid") == [newest]


def test_venue_aggregation_normalizes_coordinates_and_rejects_invalid_locations():
    data = [
        {"venue_name": "Pub", "venue_lat": 40, "venue_lng": -75},
        {"venue_name": "Pub", "venue_lat": "40.0", "venue_lng": "-75.0"},
        {"venue_name": "Outside", "venue_lat": 95, "venue_lng": -75},
        {"venue_name": "Outside", "venue_lat": 40, "venue_lng": 181},
        {"venue_name": "Boolean", "venue_lat": True, "venue_lng": -75},
        {"venue_name": "Infinite", "venue_lat": float("inf"), "venue_lng": -75},
    ]
    parser = UntappdParser(data=data)
    venues = parser.get_unique_entries("venue")
    assert len(venues) == 1
    assert venues[0]["total_venue_checkins"] == 2
    assert venues[0]["venue_lat"] == 40.0
    assert parser.to_dashboard_stats()["totals"]["unique_venues"] == 1
    assert len(parser.to_geojson(data)["features"]) == 2
    assert parser.get_stats(unique_entries=venues)["duplicates"] == 1


@pytest.mark.parametrize("link_type", ["direct", "symlink", "hardlink"])
def test_cli_does_not_overwrite_its_input(tmp_path, sample_data, monkeypatch, capsys, link_type):
    source = tmp_path / ("venues.json" if link_type == "direct" else "export.json")
    original = json.dumps(sample_data)
    source.write_text(original, encoding="utf-8")
    if link_type == "symlink":
        (tmp_path / "venues.json").symlink_to(source)
    elif link_type == "hardlink":
        (tmp_path / "venues.json").hardlink_to(source)
    monkeypatch.setattr(
        "sys.argv", ["untappd-parser", str(source), "-o", str(tmp_path), "--only", "map,json"]
    )
    with pytest.raises(SystemExit):
        cli_main()
    assert "Output would replace the input file" in capsys.readouterr().err
    assert source.read_text(encoding="utf-8") == original
    assert not (tmp_path / "beermap.html").exists()


def test_cli_empty_csv_removes_stale_csv_files_only(tmp_path, monkeypatch, capsys):
    source = tmp_path / "export.json"
    source.write_text("[]", encoding="utf-8")
    for filename in (
        "venues.csv",
        "venues-1-visit.csv",
        "venues-2-4-visits.csv",
        "venues-5-plus-visits.csv",
    ):
        (tmp_path / filename).write_text("stale", encoding="utf-8")
    (tmp_path / "beermap.html").write_text("map", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("notes", encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv", ["untappd-parser", str(source), "-o", str(tmp_path), "--only", "csv"]
    )
    cli_main()
    assert not list(tmp_path.glob("*.csv"))
    assert (tmp_path / "beermap.html").read_text(encoding="utf-8") == "map"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "notes"
    assert "Removed 4 stale" in capsys.readouterr().out


def test_csv_serialization_matches_file_export(tmp_path, parser):
    data = [{"name": "Café, Pub", "styles": ["IPA", "Stout"]}, {"name": "Other", "count": 2}]
    parser.save_csvs(data, tmp_path, "venues")
    assert UntappdParser.to_csv(data).encode() == (tmp_path / "venues.csv").read_bytes()
    assert next(csv.DictReader(UntappdParser.to_csv(data).splitlines()))["styles"] == "IPA; Stout"
