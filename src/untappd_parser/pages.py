from __future__ import annotations

import json
from importlib import resources
from typing import Any

VENUE_DATA_SENTINEL = '"__UNTAPPD_VENUE_DATA__"'
STATS_DATA_SENTINEL = '"__UNTAPPD_STATS_DATA__"'
SIBLING_LINK_SENTINEL = "<!--__UNTAPPD_SIBLING_LINK__-->"

BEERMAP_FILENAME = "beermap.html"
BEERSTATS_FILENAME = "beerstats.html"


def _render(template_name: str, sentinel: str, payload: Any, sibling_link: str) -> str:
    template = (resources.files(__package__) / "templates" / template_name).read_text(
        encoding="utf-8"
    )
    if template.count(sentinel) != 1:
        raise ValueError(f"{template_name} does not hold exactly one {sentinel} placeholder")
    # json.dumps emits < > & only inside string literals, so a blanket escape is safe here.
    # It stops a venue name that holds "</script>" from closing the data block early.
    payload_json = (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return template.replace(sentinel, payload_json).replace(SIBLING_LINK_SENTINEL, sibling_link)


def render_beermap(geojson: dict[str, Any], link_to_stats: bool = False) -> str:
    link = (
        f'<div class="panel sibling"><a href="{BEERSTATS_FILENAME}">Stats &rarr;</a></div>'
        if link_to_stats
        else ""
    )
    return _render(BEERMAP_FILENAME, VENUE_DATA_SENTINEL, geojson, link)


def render_beerstats(stats: dict[str, Any], link_to_map: bool = False) -> str:
    link = (
        f'<p class="sibling"><a href="{BEERMAP_FILENAME}">Map &rarr;</a></p>' if link_to_map else ""
    )
    return _render(BEERSTATS_FILENAME, STATS_DATA_SENTINEL, stats, link)
