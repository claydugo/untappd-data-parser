import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class VenueLocation:
    name: str
    latitude: float
    longitude: float

    def __hash__(self) -> int:
        return hash((self.name, self.latitude, self.longitude))


class UntappdParser:
    desired_keys: set[str] = {
        "beer_name",
        "brewery_name",
        "beer_type",
        "venue_name",
        "venue_lat",
        "venue_lng",
        "created_at",
        "total_venue_checkins",
        "first_checkin",
        "last_checkin",
    }

    def __init__(
        self,
        data: Optional[List[Dict[str, Any]]] = None,
        filename: Optional[Union[str, Path]] = None,
    ):
        if data is not None:
            self.data: List[Dict[str, Any]] = data
        elif filename is not None:
            self.filename: Path = Path(filename)
            self.data: List[Dict[str, Any]] = self._load_data()
        else:
            raise ValueError("Either data or filename must be provided")

    def _load_data(self) -> List[Dict[str, Any]]:
        with open(self.filename, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_unique_entries(self, key: str) -> List[Dict[str, Any]]:
        if key == "venue":
            return self._get_unique_venues()

        # Filter out entries where the key value is None or missing
        return list(
            {entry[key]: entry for entry in self.data if entry.get(key) is not None}.values()
        )

    def _get_unique_venues(self) -> List[Dict[str, Any]]:
        venue_checkins: defaultdict[VenueLocation, int] = defaultdict(int)
        venue_data: Dict[VenueLocation, Dict[str, Any]] = {}
        venue_dates: defaultdict[VenueLocation, List[str]] = defaultdict(list)

        for entry in self.data:
            venue = VenueLocation(
                name=entry["venue_name"],
                latitude=entry["venue_lat"],
                longitude=entry["venue_lng"],
            )
            venue_checkins[venue] += 1
            venue_data[venue] = entry
            if "created_at" in entry:
                venue_dates[venue].append(entry["created_at"])

        result = []
        for venue, entry in venue_data.items():
            entry_copy = entry.copy()
            entry_copy["total_venue_checkins"] = venue_checkins[venue]

            dates = venue_dates[venue]
            if dates:
                dates.sort()
                entry_copy["first_checkin"] = dates[0]
                entry_copy["last_checkin"] = dates[-1] if len(dates) > 1 else None

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
        if not data:
            return data
        backend_keys = set(data[0].keys()) - self.desired_keys
        return [{k: v for k, v in entry.items() if k not in backend_keys} for entry in data]

    @staticmethod
    def _format_dates(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def format_date_string(date_str: str) -> str:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").strftime("%B %d, %Y at %I:%M%p")

        for entry in data:
            if date := entry.pop("created_at", None):
                pass

            if first_date := entry.pop("first_checkin", None):
                entry["First Check-in"] = format_date_string(first_date)

            if last_date := entry.pop("last_checkin", None):
                entry["Last Check-in"] = format_date_string(last_date)

        return data

    @staticmethod
    def _humanize_keys(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [{k.replace("_", " ").title(): v for k, v in entry.items()} for entry in data]

    def get_visit_distribution(self, data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        single_visit: List[Dict[str, Any]] = []
        two_to_four_visits: List[Dict[str, Any]] = []
        five_plus_visits: List[Dict[str, Any]] = []

        for entry in data:
            total_visits = entry.get("Total Venue Checkins", entry.get("total_venue_checkins", 0))
            if total_visits == 1:
                single_visit.append(entry)
            elif 2 <= total_visits <= 4:
                two_to_four_visits.append(entry)
            elif total_visits >= 5:
                five_plus_visits.append(entry)

        return {
            "1_visit": single_visit,
            "2-4_visits": two_to_four_visits,
            "5+_visits": five_plus_visits,
        }

    def save_files(
        self, data: List[Dict[str, Any]], base_filename: str, split_by_visits: bool = False
    ) -> None:
        with open(f"{base_filename}.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        if split_by_visits and "venue" in base_filename:
            self._save_visit_distribution_csvs(data, base_filename)
        else:
            self._save_csv(data, f"{base_filename}.csv")

    def _save_csv(self, data: List[Dict[str, Any]], filename: str) -> None:
        if not data:
            return

        fieldnames = list(data[0].keys())
        with open(filename, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    def _save_visit_distribution_csvs(self, data: List[Dict[str, Any]], base_filename: str) -> None:
        distribution = self.get_visit_distribution(data)

        distributions = [
            (distribution["1_visit"], f"{base_filename}_1_visit.csv", "1 visit"),
            (distribution["2-4_visits"], f"{base_filename}_2-4_visits.csv", "2-4 visits"),
            (distribution["5+_visits"], f"{base_filename}_5+_visits.csv", "5+ visits"),
        ]

        for venues, filename, desc in distributions:
            if venues:
                self._save_csv(venues, filename)
                print(f"  - {desc}: {len(venues)} venues saved to {filename}")

    def get_stats(self) -> Dict[str, int]:
        unique_venues = self.get_unique_entries("venue")
        return {
            "total_checkins": len(self.data),
            "unique_venues": len(unique_venues),
            "duplicates": len(self.data) - len(unique_venues),
        }
