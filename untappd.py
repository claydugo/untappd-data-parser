#!/usr/bin/env python3
from __future__ import annotations
import json
import csv
import argparse
import os
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass
from collections import defaultdict


@dataclass
class VenueLocation:
    name: str
    latitude: float
    longitude: float

    def __hash__(self) -> int:
        return hash((self.name, self.latitude, self.longitude))


class UntappdParser:
    DESIRED_KEYS = {
        "beer_name",
        "brewery_name",
        "beer_type",
        "venue_name",
        "venue_lat",
        "venue_lng",
        "created_at",
    }

    def __init__(self, filename: str):
        self.filename = filename
        self.data = self._load_data()

    def _load_data(self) -> List[Dict[str, Any]]:
        with open(self.filename) as f:
            return json.load(f)

    def get_unique_entries(self, key: str) -> List[Dict[str, Any]]:
        if key == "venue":
            return self._get_unique_venues()

        return list({entry[key]: entry for entry in self.data}.values())

    def _get_unique_venues(self) -> List[Dict[str, Any]]:
        venue_checkins = defaultdict(int)
        venue_data = {}

        for entry in self.data:
            venue = VenueLocation(
                name=entry["venue_name"],
                latitude=entry["venue_lat"],
                longitude=entry["venue_lng"],
            )
            venue_checkins[venue] += 1
            venue_data[venue] = entry

        result = []
        for venue, entry in venue_data.items():
            entry_copy = entry.copy()
            entry_copy["total_venue_checkins"] = venue_checkins[venue]
            result.append(entry_copy)

        return result

    def clean_data(
        self,
        data: List[Dict[str, Any]],
        strip_backend: bool = True,
        fancy_dates: bool = True,
        human_keys: bool = True,
    ) -> List[Dict[str, Any]]:
        result = data.copy()

        if strip_backend:
            result = self._strip_backend_keys(result)
        if fancy_dates:
            result = self._format_dates(result)
        if human_keys:
            result = self._humanize_keys(result)

        return result

    def _strip_backend_keys(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        backend_keys = set(data[0].keys()) - self.DESIRED_KEYS
        return [
            {k: v for k, v in entry.items() if k not in backend_keys} for entry in data
        ]

    @staticmethod
    def _format_dates(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for entry in data:
            if date := entry.pop("created_at", None):
                formatted_date = datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime(
                    "%B %d, %Y at %I:%M%p"
                )
                entry["Date Drank"] = formatted_date
        return data

    @staticmethod
    def _humanize_keys(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {k.replace("_", " ").title(): v for k, v in entry.items()} for entry in data
        ]

    def save_files(self, data: List[Dict[str, Any]], key: str) -> None:
        base_filename = f"{os.path.splitext(self.filename)[0]}_unique_{key}"

        with open(f"{base_filename}.json", "w") as f:
            json.dump(data, f, indent=2)

        fieldnames = list(data[0].keys())
        with open(f"{base_filename}.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)


if __name__ == "__main__":
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
    parser.add_argument(
        "--no-fancy-dates", action="store_true", help="Keep original date format"
    )
    parser.add_argument(
        "--no-human-keys", action="store_true", help="Keep original key names"
    )

    args = parser.parse_args()

    parser = UntappdParser(args.file)
    unique_entries = parser.get_unique_entries(args.key)

    cleaned_data = parser.clean_data(
        unique_entries,
        strip_backend=not args.no_strip_backend,
        fancy_dates=not args.no_fancy_dates,
        human_keys=not args.no_human_keys,
    )

    parser.save_files(cleaned_data, args.key)

    total_entries = len(parser.data)
    unique_count = len(unique_entries)
    print(f"Total check-ins: {total_entries}")
    print(f"Unique {args.key}s: {unique_count}")
    print(f"Duplicates: {total_entries - unique_count}")
