"""Tests for the Untappd export parser.

The sample below mirrors the shape of a real Untappd JSON export: the fields the
parser cares about plus a couple of "backend" keys that `strip_backend` drops.
"""

import csv
import json
from pathlib import Path

import pytest

from untappd_parser import UntappdParser, VenueLocation


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
    base = str(tmp_path / "out_unique_venue")
    parser.save_files(cleaned, base)

    with Path(f"{base}.csv").open(encoding="utf-8") as f:
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
    base = str(tmp_path / "out")
    parser.save_files(cleaned, base, split_by_visits=True)
    assert Path(f"{base}_1_visit.csv").exists()
    assert Path(f"{base}_2-4_visits.csv").exists()
    assert Path(f"{base}_5+_visits.csv").exists()


def test_split_by_visits_falls_back_to_single_csv_without_visit_counts(tmp_path, parser):
    # Non-venue data matches no visit bucket; a single CSV must be written, not none.
    breweries = parser.get_unique_entries("brewery_name")
    cleaned = parser.clean_data(breweries, preserve_keys={"brewery_name"})
    base = str(tmp_path / "out_unique_brewery_name")
    parser.save_files(cleaned, base, split_by_visits=True)

    with Path(f"{base}.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert not list(tmp_path.glob("*_visit*.csv"))


def test_stats_accept_precomputed_unique_entries(parser):
    unique_entries = parser.get_unique_entries("venue")
    assert parser.get_stats(unique_entries=unique_entries) == parser.get_stats()


def test_save_files_writes_json_and_split_csvs(tmp_path, parser):
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues)
    base = str(tmp_path / "out_unique_venue")
    parser.save_files(cleaned, base, split_by_visits=True)

    assert json.loads(Path(f"{base}.json").read_text(encoding="utf-8"))
    with Path(f"{base}_5+_visits.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [row["Venue Name"] for row in rows] == ["The Cellar"]
