from __future__ import annotations

import csv
import json
import math
from collections import Counter
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
        venue_beers: dict[VenueLocation, set[str]] = {}
        venue_breweries: dict[VenueLocation, set[str]] = {}
        venue_styles: dict[VenueLocation, Counter[str]] = {}
        venue_abv: dict[VenueLocation, list[float]] = {}
        # (created_at, beer_name, brewery_name) of the newest check-in per venue.
        venue_last_beer: dict[VenueLocation, tuple[str, str, str | None]] = {}
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
                venue_beers[venue] = set()
                venue_breweries[venue] = set()
                venue_styles[venue] = Counter()
                venue_abv[venue] = []
            else:
                venue_info[venue]["total_venue_checkins"] += 1
                if entry.get("created_at"):
                    venue_info[venue]["checkin_dates"].append(entry["created_at"])

            if entry.get("beer_name"):
                # bid distinguishes different beers that share a name.
                venue_beers[venue].add(entry.get("bid") or entry["beer_name"])
                created_at = entry.get("created_at") or ""
                newest = venue_last_beer.get(venue)
                if newest is None or (created_at and created_at >= newest[0]):
                    venue_last_beer[venue] = (
                        created_at,
                        entry["beer_name"],
                        entry.get("brewery_name"),
                    )
            if entry.get("brewery_name"):
                venue_breweries[venue].add(entry["brewery_name"])
            if entry.get("beer_type"):
                venue_styles[venue][entry["beer_type"]] += 1
            abv = self._as_positive_float(entry.get("beer_abv"))
            if abv is not None:
                venue_abv[venue].append(abv)

        result = []
        for venue, info in venue_info.items():
            dates = info["checkin_dates"]
            dates.sort()

            if dates:
                info["first_checkin"] = dates[0]
                info["last_checkin"] = dates[-1] if len(dates) > 1 else None

            info["unique_beers"] = len(venue_beers[venue])
            info["unique_breweries"] = len(venue_breweries[venue])
            info["top_styles"] = [style for style, _ in venue_styles[venue].most_common(3)]
            if venue_abv[venue]:
                info["average_abv"] = round(sum(venue_abv[venue]) / len(venue_abv[venue]), 1)
            if venue in venue_last_beer:
                _, info["last_beer_name"], info["last_beer_brewery"] = venue_last_beer[venue]
            result.append(info)

        return result

    @staticmethod
    def _as_positive_float(value: Any) -> float | None:
        # Untappd leaves unknown ABV/IBU/rating as 0 or ""; both mean "no data".
        # A non-finite value would poison averages and serialize as a bare
        # Infinity token that browser JSON.parse rejects.
        if isinstance(value, bool):
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number > 0 and math.isfinite(number) else None

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

    def to_geojson(self, data: list[dict[str, Any]]) -> dict[str, Any]:
        features = []
        for entry in data:
            latitude = entry.get("venue_lat")
            longitude = entry.get("venue_lng")
            if latitude is None or longitude is None:
                continue
            # NaN would serialize as a bare token JSON.parse rejects; coerce and skip.
            try:
                latitude = float(latitude)
                longitude = float(longitude)
            except (TypeError, ValueError):
                continue
            if not (math.isfinite(latitude) and math.isfinite(longitude)):
                continue
            properties = {
                key: entry[key]
                for key in (
                    "venue_name",
                    "venue_city",
                    "venue_state",
                    "venue_country",
                    "total_venue_checkins",
                    "unique_beers",
                    "unique_breweries",
                    "top_styles",
                    "average_abv",
                    "last_beer_name",
                    "last_beer_brewery",
                    "first_checkin",
                    "last_checkin",
                    "checkin_dates",
                )
                if entry.get(key) is not None
            }
            # Publish dates at day precision; full timestamps stay private.
            for key in ("first_checkin", "last_checkin"):
                if key in properties:
                    properties[key] = str(properties[key])[:10]
            if "checkin_dates" in properties:
                properties["checkin_dates"] = [
                    str(date)[:10] for date in properties["checkin_dates"]
                ]
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
                    "properties": properties,
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def save_geojson(self, data: list[dict[str, Any]], filename: str) -> None:
        # indent=1 keeps refresh diffs readable when the file is committed to a site repo.
        with Path(filename).open("w", encoding="utf-8") as f:
            json.dump(self.to_geojson(data), f, ensure_ascii=False, indent=1)

    def to_dashboard_stats(self) -> dict[str, Any]:
        checkins_per_day: Counter[str] = Counter()
        weekday_hour = [[0] * 24 for _ in range(7)]
        abv_counts = [0] * 32  # 0.5% bins; the last bin is 15.5%+
        ibu_counts = [0] * 13  # 10 IBU bins; the last bin is 120+
        my_rating_counts = [0] * 21  # 0.25 bins over 0-5
        global_rating_counts = [0] * 21
        abv_values: list[float] = []
        my_rating_values: list[float] = []
        global_rating_values: list[float] = []
        brewery_checkins: Counter[str] = Counter()
        brewery_beers: dict[str, set[Any]] = {}
        brewery_countries: Counter[str] = Counter()
        flavor_counts: Counter[str] = Counter()
        flavor_tagged_checkins = 0
        unique_beers: set[Any] = set()

        for entry in self.data:
            created_at = entry.get("created_at")
            if created_at:
                try:
                    moment = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")  # noqa: DTZ007
                except (TypeError, ValueError):
                    moment = None
                if moment is not None:
                    checkins_per_day[moment.strftime("%Y-%m-%d")] += 1
                    weekday_hour[moment.weekday()][moment.hour] += 1

            abv = self._as_positive_float(entry.get("beer_abv"))
            if abv is not None:
                abv_values.append(abv)
                abv_counts[min(int(abv / 0.5), 31)] += 1

            ibu = self._as_positive_float(entry.get("beer_ibu"))
            if ibu is not None:
                ibu_counts[min(int(ibu / 10), 12)] += 1

            rating = self._as_positive_float(entry.get("rating_score"))
            if rating is not None:
                my_rating_values.append(rating)
                my_rating_counts[min(int(rating / 0.25), 20)] += 1

            global_rating = self._as_positive_float(entry.get("global_weighted_rating_score"))
            if global_rating is not None:
                global_rating_values.append(global_rating)
                global_rating_counts[min(int(global_rating / 0.25), 20)] += 1

            beer_id = entry.get("bid") or entry.get("beer_name")
            if beer_id:
                unique_beers.add(beer_id)
            if entry.get("brewery_name"):
                brewery = entry["brewery_name"]
                brewery_checkins[brewery] += 1
                if beer_id:
                    brewery_beers.setdefault(brewery, set()).add(beer_id)
            if entry.get("brewery_country"):
                brewery_countries[entry["brewery_country"]] += 1
            if entry.get("flavor_profiles"):
                flavor_tagged_checkins += 1
                for flavor in str(entry["flavor_profiles"]).split(","):
                    if flavor.strip():
                        flavor_counts[flavor.strip()] += 1

        def mean(values: list[float], digits: int) -> float | None:
            return round(sum(values) / len(values), digits) if values else None

        days = sorted(checkins_per_day)
        return {
            "totals": {
                "checkins": len(self.data),
                "unique_beers": len(unique_beers),
                "unique_breweries": len(brewery_checkins),
                "unique_venues": len(self._get_unique_venues()),
                "first_day": days[0] if days else None,
                "last_day": days[-1] if days else None,
                "average_abv": mean(abv_values, 1),
                "average_rating": mean(my_rating_values, 2),
                "average_global_rating": mean(global_rating_values, 2),
                "flavor_tagged_checkins": flavor_tagged_checkins,
            },
            "checkins_per_day": dict(checkins_per_day),
            "weekday_hour": weekday_hour,
            "abv_histogram": {"start": 0, "bin_width": 0.5, "counts": abv_counts},
            "ibu_histogram": {"start": 0, "bin_width": 10, "counts": ibu_counts},
            "rating_histograms": {
                "start": 0,
                "bin_width": 0.25,
                "mine": my_rating_counts,
                "global": global_rating_counts,
            },
            "top_breweries": [
                {
                    "name": name,
                    "checkins": count,
                    "unique_beers": len(brewery_beers.get(name, set())),
                }
                for name, count in brewery_checkins.most_common(20)
            ],
            "brewery_countries": [
                {"country": country, "checkins": count}
                for country, count in brewery_countries.most_common()
            ],
            "flavor_profiles": [
                {"flavor": flavor, "checkins": count}
                for flavor, count in flavor_counts.most_common(20)
            ],
        }

    def save_dashboard_stats(self, filename: str) -> None:
        with Path(filename).open("w", encoding="utf-8") as f:
            json.dump(self.to_dashboard_stats(), f, ensure_ascii=False, indent=1)

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
        # List values (checkin_dates, top_styles) would render as Python reprs.
        rows = [
            {
                key: "; ".join(str(item) for item in value) if isinstance(value, list) else value
                for key, value in entry.items()
            }
            for entry in data
        ]
        with Path(filename).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

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
