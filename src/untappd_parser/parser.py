from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, cast


@dataclass(frozen=True)
class VenueLocation:
    name: str
    latitude: float
    longitude: float


class UntappdParser:
    desired_keys: ClassVar[set[str]] = {
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
        data: list[dict[str, Any]] | None = None,
        filename: str | Path | None = None,
    ):
        if data is not None:
            self.data: list[dict[str, Any]] = data
        elif filename is not None:
            self.filename: Path = Path(filename)
            self.data = self._load_data()
        else:
            raise ValueError("Either data or filename must be provided")

    def _load_data(self) -> list[dict[str, Any]]:
        with self.filename.open(encoding="utf-8") as f:
            return cast("list[dict[str, Any]]", json.load(f))

    def get_unique_entries(self, key: str) -> list[dict[str, Any]]:
        if key == "venue":
            return self._get_unique_venues()

        return list(
            {entry[key]: entry for entry in self.data if entry.get(key) is not None}.values()
        )

    def _get_unique_venues(self) -> list[dict[str, Any]]:
        venue_info: dict[VenueLocation, dict[str, Any]] = {}
        for entry in self.data:
            venue_name = entry.get("venue_name")
            venue_lat = entry.get("venue_lat")
            venue_lng = entry.get("venue_lng")

            if venue_name is None or venue_lat is None or venue_lng is None:
                continue

            venue = VenueLocation(
                name=venue_name,
                latitude=venue_lat,
                longitude=venue_lng,
            )

            if venue not in venue_info:
                venue_info[venue] = {
                    **entry,
                    "total_venue_checkins": 1,
                    "checkin_dates": [entry.get("created_at")] if entry.get("created_at") else [],
                }
            else:
                venue_info[venue]["total_venue_checkins"] += 1
                if entry.get("created_at"):
                    venue_info[venue]["checkin_dates"].append(entry["created_at"])

        result = []
        for info in venue_info.values():
            dates = info.pop("checkin_dates", [])

            if dates:
                dates.sort()
                info["first_checkin"] = dates[0]
                info["last_checkin"] = dates[-1] if len(dates) > 1 else None

            result.append(info)

        return result

    def clean_data(
        self,
        data: list[dict[str, Any]],
        strip_backend: bool = True,
        fancy_dates: bool = True,
        human_keys: bool = True,
        preserve_keys: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        result = data.copy()

        if strip_backend:
            result = self._strip_backend_keys(result, preserve_keys)
        if fancy_dates:
            result = self._format_dates(result)
        if human_keys:
            result = self._humanize_keys(result)

        return result

    def _strip_backend_keys(
        self, data: list[dict[str, Any]], preserve_keys: set[str] | None = None
    ) -> list[dict[str, Any]]:
        if not data:
            return data
        keep = self.desired_keys | (preserve_keys or set())
        all_keys = {key for entry in data for key in entry}
        backend_keys = all_keys - keep
        return [{k: v for k, v in entry.items() if k not in backend_keys} for entry in data]

    @staticmethod
    def _format_dates(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def format_date_string(date_str: str) -> str | None:
            try:
                return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S").strftime(  # noqa: DTZ007
                    "%B %d, %Y at %I:%M%p"
                )
            except (ValueError, TypeError):
                return None

        for entry in data:
            if first_date := entry.get("first_checkin"):
                formatted_first = format_date_string(first_date)
                if formatted_first:
                    entry.pop("first_checkin", None)
                    entry["First Checkin"] = formatted_first

            if last_date := entry.get("last_checkin"):
                formatted_last = format_date_string(last_date)
                if formatted_last:
                    entry.pop("last_checkin", None)
                    entry["Last Checkin"] = formatted_last

            if "First Checkin" in entry or "Last Checkin" in entry:
                entry.pop("created_at", None)

        return data

    @staticmethod
    def _humanize_keys(data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k.replace("_", " ").title(): v for k, v in entry.items()} for entry in data]

    def get_visit_distribution(self, data: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        single_visit: list[dict[str, Any]] = []
        two_to_four_visits: list[dict[str, Any]] = []
        five_plus_visits: list[dict[str, Any]] = []

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
        self, data: list[dict[str, Any]], base_filename: str, split_by_visits: bool = False
    ) -> None:
        with Path(f"{base_filename}.json").open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # Non-venue rows have no visit counts and land in no bucket; fall back to a single CSV.
        wrote_split = split_by_visits and self._save_visit_distribution_csvs(data, base_filename)
        if not wrote_split:
            self._save_csv(data, f"{base_filename}.csv")

    def _save_csv(self, data: list[dict[str, Any]], filename: str) -> None:
        if not data:
            return

        # Rows can have heterogeneous key sets; union them so DictWriter never raises.
        fieldnames = list(dict.fromkeys(key for entry in data for key in entry))
        with Path(filename).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)

    def _save_visit_distribution_csvs(self, data: list[dict[str, Any]], base_filename: str) -> bool:
        distribution = self.get_visit_distribution(data)

        distributions = [
            (distribution["1_visit"], f"{base_filename}_1_visit.csv", "1 visit"),
            (distribution["2-4_visits"], f"{base_filename}_2-4_visits.csv", "2-4 visits"),
            (distribution["5+_visits"], f"{base_filename}_5+_visits.csv", "5+ visits"),
        ]

        wrote_any = False
        for venues, filename, desc in distributions:
            if venues:
                self._save_csv(venues, filename)
                print(f"  - {desc}: {len(venues)} venues saved to {filename}")
                wrote_any = True
        return wrote_any

    def get_stats(
        self, key: str = "venue", unique_entries: list[dict[str, Any]] | None = None
    ) -> dict[str, int]:
        if unique_entries is None:
            unique_entries = self.get_unique_entries(key)
        if key == "venue":
            # Each unique venue carries its check-in count; summing gives valid-venue check-ins.
            counted = sum(
                entry.get("Total Venue Checkins", entry.get("total_venue_checkins", 0))
                for entry in unique_entries
            )
        else:
            counted = sum(1 for entry in self.data if entry.get(key) is not None)
        return {
            "total_checkins": len(self.data),
            f"unique_{key}s": len(unique_entries),
            "duplicates": counted - len(unique_entries),
        }
