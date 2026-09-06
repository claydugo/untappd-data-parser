import io
import json
import os
import re
import shutil
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

from untappd_parser import UntappdParser
from untappd_parser.pages import render_beermap, render_beerstats


@pytest.fixture(scope="module")
def checkins():
    return [
        {
            "venue_name": venue,
            "venue_lat": latitude,
            "venue_lng": longitude,
            "venue_state": state,
            "venue_country": country,
            "created_at": date,
            "beer_name": beer,
            "bid": identifier,
            "brewery_name": brewery,
            "beer_type": style,
            "beer_abv": abv,
            "beer_ibu": 200,
            "rating_score": 5 if identifier == 1 else 0,
            "global_weighted_rating_score": 5 if identifier == 1 else 1,
            "serving_type": serving,
        }
        for (
            venue,
            latitude,
            longitude,
            state,
            country,
            date,
            beer,
            identifier,
            brewery,
            style,
            abv,
            serving,
        ) in [
            (
                "Tavern",
                40,
                -75,
                "Pennsylvania",
                "United States",
                "2020-03-09 18:00:00",
                "First IPA",
                1,
                "Café 🍺",
                "IPA - American",
                6,
                "Draft",
            ),
            (
                "Tavern",
                40,
                -75,
                "Pennsylvania",
                "United States",
                "2024-03-10 18:00:00",
                "Hazy IPA",
                2,
                "Brewery B",
                "IPA - New England / Hazy",
                8,
                "Draft",
            ),
            (
                "Tavern",
                40,
                -75,
                "Pennsylvania",
                "United States",
                "2024-03-10 20:00:00",
                "Stout",
                3,
                "Brewery C",
                "Stout - Imperial / Double",
                12,
                "Bottle",
            ),
            (
                "Tavern",
                40,
                -75,
                "Pennsylvania",
                "United States",
                "2024-04-10 18:00:00",
                "Hazy IPA",
                2,
                "Brewery B",
                "IPA - New England / Hazy",
                None,
                "Can",
            ),
            (
                "Pub",
                40,
                -75.5,
                "Ontario",
                "Canada",
                "2024-03-10 18:00:00",
                "Pub Stout",
                4,
                "Brewery C",
                "Stout - Imperial / Double",
                10,
                "Draft",
            ),
            (
                "Untappd at Home",
                34,
                -77,
                "NC",
                "United States",
                "2024-03-11 18:00:00",
                "Home Beer",
                5,
                "Home Brewery",
                "Barleywine - American",
                20,
                "Bottle",
            ),
        ]
    ]


@pytest.fixture(scope="module")
def site(tmp_path_factory, checkins):
    directory = tmp_path_factory.mktemp("browser")
    project = Path(__file__).resolve().parents[1]
    (directory / "src").symlink_to(project / "src", target_is_directory=True)
    shutil.copyfile(project / "untappd.html", directory / "untappd.html")
    shutil.copyfile(project / "style.css", directory / "style.css")
    (directory / "favicon.ico").write_bytes(b"")
    (directory / "export.json").write_text(
        json.dumps(checkins, ensure_ascii=False), encoding="utf-8"
    )
    parser = UntappdParser(data=checkins)
    (directory / "beermap.html").write_text(
        render_beermap(
            parser.to_geojson(parser.get_unique_entries("venue"), exclude_untappd_at_home=True)
        ),
        encoding="utf-8",
    )
    (directory / "beerstats.html").write_text(
        render_beerstats(parser.to_dashboard_stats()), encoding="utf-8"
    )
    (directory / "empty.html").write_text(
        render_beermap({"type": "FeatureCollection", "features": []}), encoding="utf-8"
    )
    with ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=directory)
    ) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}", directory
        finally:
            server.shutdown()
            thread.join()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=os.environ.get("BROWSER_EXECUTABLE"))
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        color_scheme="dark",
        locale="en-US",
        timezone_id="America/New_York",
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on(
        "console", lambda message: errors.append(message.text) if message.type == "error" else None
    )
    yield page
    context.close()
    assert errors == []


def wait_for_map(page):
    page.wait_for_function(
        "() => window.beermap?.loaded() && !window.beermap.isMoving()"
        " && !document.getElementById('map-controls').hidden"
    )


def inlined_json(page, identifier):
    return json.loads(
        re.search(
            f'<script type="application/json" id="{identifier}">(.*?)</script>', page, re.DOTALL
        )[1]
    )


def test_date_keyboard_entry_and_paused_links(page, site):
    origin, _ = site
    page.goto(f"{origin}/beermap.html#3/40/-75.25")
    wait_for_map(page)
    start = page.locator("#date-start")
    start.focus()
    page.keyboard.press("ArrowRight")
    page.keyboard.press("ArrowRight")
    page.keyboard.type("2022", delay=30)
    expect(start).to_have_value("2022-03-09")
    page.keyboard.press("Tab")
    expect(page.locator("#stats")).to_contain_text("4 check-ins")
    page.locator("#date-end").fill("2024-03-10")
    page.locator("#date-end").press("Enter")
    expect(page.locator("#stats")).to_contain_text("3 check-ins")
    start.fill("")
    expect(start).to_have_value("")
    expect(page.locator("#stats")).to_contain_text("3 check-ins")
    page.locator("#date-end").focus()
    expect(start).to_have_value("2020-03-09")
    expect(page.locator("#stats")).to_contain_text("4 check-ins")
    page.locator("#reset-filters").click()
    expect(page.locator("#stats")).to_contain_text("5 check-ins")
    page.locator("#play-button").click()
    page.wait_for_function(
        "() => document.getElementById('time-label').textContent.includes('Through')"
    )
    page.locator("#play-button").click()
    page.wait_for_url(lambda address: "at" in parse_qs(urlsplit(address).query))
    label = page.locator("#time-label").inner_text()
    statistics = page.locator("#stats").inner_text()
    page.reload()
    wait_for_map(page)
    expect(page.locator("#time-label")).to_have_text(label)
    expect(page.locator("#stats")).to_have_text(statistics, use_inner_text=True)
    expect(page.locator("#play-button")).to_have_attribute("aria-label", "Play")
    page.goto(f"{origin}/beermap.html?from=2030-01-01&through=2031-01-01")
    wait_for_map(page)
    expect(start).to_have_value("2024-04-10")
    expect(page.locator("#stats")).to_contain_text("1 check-in")


def test_filtered_popups_clusters_and_lazy_sources(page, site):
    origin, _ = site
    page.goto(f"{origin}/beermap.html#3/40/-75.25")
    wait_for_map(page)
    assert (
        page.evaluate(
            "async () => (await window.beermap.getSource('venues-heat').getData()).features.length"
        )
        == 0
    )
    page.wait_for_function(
        "() => window.beermap.queryRenderedFeatures({layers:['clusters']}).length > 0"
    )
    cluster = page.evaluate(
        "window.beermap.queryRenderedFeatures({layers:['clusters']})[0].properties"
    )
    assert (cluster["total_venue_checkins"], cluster["abv_sum"], cluster["abv_count"]) == (5, 36, 4)
    colors = page.evaluate("""() => {
        const feature = window.beermap.queryRenderedFeatures({layers:['clusters']})[0];
        return [
            window.beermap.getLayer('clusters').paint.get('circle-color')
                .evaluate(feature).toString(),
            getComputedStyle(document.getElementById('legend-dot-3')).backgroundColor,
        ];
    }""")
    assert colors[0].replace(" ", "").replace("rgba(", "rgb(").replace(",1)", ")") == colors[
        1
    ].replace(" ", "")
    page.locator("#metric-abv").click()
    page.wait_for_function(
        "() => window.beermap.getLayer('cluster-counts').layout.get('text-field')"
        ".evaluate(window.beermap.queryRenderedFeatures({layers:['clusters']})[0])"
        ".toString() === '9.0%'"
    )
    page.locator("#date-start").fill("2024-03-10")
    page.locator("#date-start").press("Enter")
    page.locator("#date-end").fill("2024-03-10")
    page.locator("#date-end").press("Enter")
    expect(page.locator("#stats")).to_contain_text("3 check-ins")
    page.evaluate("window.beermap.jumpTo({center:[-75,40],zoom:13})")
    page.wait_for_function(
        "() => window.beermap.queryRenderedFeatures({layers:['venue-points']})"
        ".some(feature => feature.properties.venue_id === 0)"
    )
    page.evaluate("""() => {
        const feature = window.beermap.queryRenderedFeatures({layers:['venue-points']})
            .find(feature => feature.properties.venue_id === 0);
        window.beermap.fire('click', {
            point:window.beermap.project(feature.geometry.coordinates),
            lngLat:window.beermap.getCenter(), originalEvent:{},
        });
    }""")
    expect(page.locator(".maplibregl-popup-content")).to_contain_text("10.0% avg ABV")
    page.locator("#filters-button").click()
    page.locator("#style-filter").fill("IPA")
    page.locator("#style-filter").press("Enter")
    expect(page.locator(".maplibregl-popup-content")).to_contain_text("8.0% avg ABV")
    expect(page.locator(".maplibregl-popup-content")).not_to_contain_text("Stout")
    page.locator("#heatmap-button").click()
    wait_for_map(page)
    assert (
        page.evaluate(
            "async () => (await window.beermap.getSource('venues-heat').getData())"
            ".features[0].properties.average_abv"
        )
        == 8
    )
    frozen = page.evaluate("async () => await window.beermap.getSource('venues').getData()")
    page.locator("#serving-cask").click()
    expect(page.locator("#stats")).to_contain_text("0 check-ins")
    wait_for_map(page)
    assert page.evaluate("async () => await window.beermap.getSource('venues').getData()") == frozen
    assert (
        page.evaluate(
            "async () => (await window.beermap.getSource('venues-heat').getData()).features.length"
        )
        == 0
    )
    page.locator("#bubbles-button").click()
    wait_for_map(page)
    assert (
        page.evaluate(
            "async () => (await window.beermap.getSource('venues').getData()).features.length"
        )
        == 0
    )
    page.locator("#reset-filters").click()
    page.locator("#style-filter").fill("IPA")
    page.locator("#style-filter").press("Enter")
    page.locator("#serving-can").click()
    expect(page.locator("#stats")).to_contain_text("1 check-in")
    wait_for_map(page)
    unknown = page.evaluate(
        "async () => (await window.beermap.getSource('venues').getData()).features[0].properties"
    )
    assert unknown["abv_count"] == 0
    assert unknown.get("average_abv") is None
    for scheme in ("light", "dark"):
        page.emulate_media(color_scheme=scheme)
        wait_for_map(page)
        assert (
            page.evaluate(
                "async () => (await window.beermap.getSource('venues').getData())"
                ".features[0].properties.abv_count"
            )
            == 0
        )
    page.locator("#reset-filters").click()
    expect(page.locator("#stats")).to_contain_text("5 check-ins")
    wait_for_map(page)
    page.evaluate("""() => {
        window.sourceUpdates = {venues:0, 'venues-heat':0};
        for (const identifier of Object.keys(window.sourceUpdates)) {
            const source = window.beermap.getSource(identifier);
            const original = source.setData.bind(source);
            source.setData = data => { window.sourceUpdates[identifier]++; return original(data); };
        }
        const slider = document.getElementById('time-start-slider');
        for (const value of [0,1,2,3,4,5,6,7,8,9]) {
            slider.value = String(value);
            slider.dispatchEvent(new Event('input', {bubbles:true}));
        }
    }""")
    expect(page.locator("#stats")).to_contain_text("4 check-ins")
    assert page.evaluate("window.sourceUpdates") == {"venues": 1, "venues-heat": 0}
    page.evaluate("""() => {
        const slider = document.getElementById('time-start-slider');
        slider.value = '10';
        slider.dispatchEvent(new Event('input', {bubbles:true}));
    }""")
    expect(page.locator("#date-start")).to_have_value("2020-03-19")
    page.evaluate(
        "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
    )
    assert page.evaluate("window.sourceUpdates") == {"venues": 1, "venues-heat": 0}
    page.goto(f"{origin}/empty.html")
    wait_for_map(page)
    expect(page.locator("#stats")).to_contain_text("0 check-ins")
    expect(page.locator("#time-control")).to_be_hidden()


@pytest.mark.parametrize("width,height", [(320, 568), (390, 844), (800, 600), (1440, 900)])
def test_map_controls_remain_accessible(page, site, width, height):
    origin, _ = site
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{origin}/beermap.html")
    wait_for_map(page)
    sidebar = page.locator(".map-sidebar").bounding_box()
    timeline = page.locator("#time-control").bounding_box()
    assert sidebar["y"] + sidebar["height"] < timeline["y"]
    assert timeline["x"] >= 0
    assert timeline["x"] + timeline["width"] <= width
    assert sidebar["height"] < (160 if width <= 600 else 300)
    expect(page.locator("#style-filter")).to_be_hidden()
    expect(page.locator("#reset-filters")).to_be_hidden()
    page.locator("#filters-button").click()
    if width <= 600:
        sheet = page.locator("#filter-sheet")
        expect(sheet).to_be_visible()
        assert sheet.bounding_box()["height"] <= height * 0.6 + 1
        expect(page.locator("#close-filters")).to_be_focused()
        page.keyboard.press("Shift+Tab")
        expect(page.locator("#style-filter")).to_be_focused()
        page.keyboard.press("Escape")
        expect(sheet).to_be_visible()
        expect(page.locator("#style-options")).to_be_hidden()
        page.keyboard.press("Escape")
        expect(sheet).to_be_hidden()
        expect(page.locator("#filters-button")).to_be_focused()
        page.locator("#filters-button").click()
    for identifier in ("legend", "serving-draft", "style-filter"):
        page.locator(f"#{identifier}").scroll_into_view_if_needed()
        assert page.evaluate(
            """identifier => {
            const element = document.getElementById(identifier);
            const rectangle = element.getBoundingClientRect();
            const hit = document.elementFromPoint(
                rectangle.x + rectangle.width / 2, rectangle.y + rectangle.height / 2,
            );
            return element === hit || element.contains(hit);
        }""",
            identifier,
        )
    page.locator("#style-filter").fill("IPA")
    page.locator("#style-filter").press("Enter")
    expect(page.locator("#stats")).to_contain_text("3 check-ins")
    page.locator("#serving-draft").click()
    expect(page.locator("#stats")).to_contain_text("2 check-ins")
    if width > 600:
        sidebar = page.locator(".map-sidebar").bounding_box()
        assert sidebar["y"] + sidebar["height"] < timeline["y"]
    page.locator("#close-filters" if width <= 600 else "#filters-button").click()
    expect(page.locator("#filter-chips")).to_be_visible()
    page.get_by_role("button", name="Remove IPA style filter").click()
    expect(page.locator("#stats")).to_contain_text("3 check-ins")
    expect(page.get_by_role("button", name="Remove Draft serving filter")).to_be_focused()
    page.get_by_role("button", name="Remove Draft serving filter").click()
    expect(page.locator("#stats")).to_contain_text("5 check-ins")
    expect(page.locator("#reset-filters")).to_be_hidden()
    expect(page.locator("#filters-button")).to_be_focused()
    page.locator("#time-start-slider").focus()
    page.keyboard.press("ArrowRight")
    expect(page.locator("#stats")).to_contain_text("4 check-ins")
    expect(page.get_by_role("button", name="Remove date filter")).to_be_visible()
    if width <= 600:
        expect(page.locator("#date-start")).to_be_hidden()
        page.locator("#dates-button").click()
        expect(page.locator("#date-start")).to_be_visible()
    page.locator("#reset-filters").click()
    expect(page.locator("#stats")).to_contain_text("5 check-ins")
    expect(page.locator("#filter-chips")).to_be_hidden()


def test_mobile_sheet_preserves_view_and_touch_access(browser, site):
    origin, _ = site
    with browser.new_context(
        viewport={"width": 320, "height": 568}, has_touch=True, is_mobile=True
    ) as context:
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(f"{origin}/beermap.html?metric=abv&style=IPA&serving=draft")
        wait_for_map(page)
        expect(page.locator("#stats")).to_contain_text("2 check-ins")
        expect(page.locator("#display-summary")).to_have_text("Bubbles · Avg ABV")
        page.locator("#filters-button").click()
        page.locator("#heatmap-button").click()
        page.locator("#close-filters").click()
        expect(page.locator("#display-summary")).to_have_text("Heatmap · Check-ins")
        page.locator("#reset-filters").click()
        expect(page.locator("#stats")).to_contain_text("5 check-ins")
        expect(page.locator("#display-summary")).to_have_text("Heatmap · Check-ins")
        page.wait_for_url(
            lambda address: parse_qs(urlsplit(address).query)
            == {"metric": ["abv"], "view": ["heatmap"]}
        )
        page.reload()
        wait_for_map(page)
        expect(page.locator("#filter-sheet")).to_be_hidden()
        expect(page.locator("#display-summary")).to_have_text("Heatmap · Check-ins")
        page.locator(".maplibregl-ctrl-attrib-button").click()
        page.wait_for_function("""() => {
            const timeline = document.getElementById('time-control').getBoundingClientRect();
            const attribution = document.querySelector('.maplibregl-ctrl-attrib')
                .getBoundingClientRect();
            return timeline.bottom < attribution.top;
        }""")
        page.locator("#play-button").click()
        expect(page.locator("#play-button")).to_have_attribute("aria-label", "Pause")
        page.locator("#play-button").click()
        page.locator("#filters-button").click()
        page.locator("#bubbles-button").click()
        expect(page.locator("#metric-abv")).to_have_attribute("aria-pressed", "true")
        page.locator("#style-filter").fill("IPA")
        page.locator("#style-filter").press("Enter")
        for identifier in (
            "close-filters",
            "bubbles-button",
            "metric-abv",
            "serving-draft",
            "style-filter",
        ):
            rectangle = page.locator(f"#{identifier}").bounding_box()
            assert rectangle["width"] >= 44
            assert rectangle["height"] >= 44
        page.locator("#close-filters").click()
        page.locator("#filters-button").click()
        page.mouse.click(310, 100)
        expect(page.locator("#filter-sheet")).to_be_hidden()
        expect(page.locator("#filters-button")).to_be_focused()
        page.locator("#filters-button").click()
        page.set_viewport_size({"width": 800, "height": 600})
        expect(page.locator("#filter-sheet")).to_be_hidden()
        expect(page.locator("#bubbles-button")).to_be_visible()
        expect(page.locator("#style-filter")).to_be_hidden()
        expect(page.locator("#filters-button")).to_have_attribute("aria-expanded", "false")
        page.locator("#filters-button").click()
        expect(page.locator("#style-filter")).to_have_value("IPA")
        assert errors == []


def test_dashboard_labels_describe_available_data(page, site):
    origin, _ = site
    page.goto(f"{origin}/beerstats.html")
    assert any(
        "15.5%+ ABV" in value
        for value in page.locator("#abv-chart [data-tip]").evaluate_all(
            "elements => elements.map(element => element.dataset.tip)"
        )
    )
    assert any(
        "120+ IBU" in value
        for value in page.locator("#ibu-chart [data-tip]").evaluate_all(
            "elements => elements.map(element => element.dataset.tip)"
        )
    )
    expect(page.locator("#ratings-note")).to_contain_text("My rated check-ins average 5.00.")
    expect(page.locator("#ratings-note")).not_to_contain_text("same beers")
    page.locator('#calendar [data-day="2024-03-10"]').hover()
    expect(page.locator("#tooltip")).to_have_text("Mar 10, 2024: 3 check-ins")
    page.locator('#calendar [data-day="2020-03-09"]').hover()
    expect(page.locator("#tooltip")).to_have_text("Mar 9, 2020: 1 check-in")


@pytest.mark.parametrize("strip_backend,human_keys", [(True, True), (False, False)])
def test_worker_exports_match_native_python(page, site, checkins, strip_backend, human_keys):
    origin, directory = site
    page.goto(f"{origin}/untappd.html")
    page.locator("#main-content").wait_for(state="visible", timeout=60000)
    assert len(page.workers) == 1
    page.locator("#stripBackend").set_checked(strip_backend)
    page.locator("#humanKeys").set_checked(human_keys)
    page.locator("#excludeUntappdAtHome").check()
    page.locator("#splitByVisits").uncheck()
    page.locator("#fileInput").set_input_files(directory / "export.json")
    expect(page.locator("#totalCheckins")).to_have_text("6")
    parser = UntappdParser(data=checkins)
    venues = parser.get_unique_entries("venue")
    cleaned = parser.clean_data(venues, strip_backend=strip_backend, human_keys=human_keys)
    for button, filename in (
        ("exportAllBtn", "venues.json"),
        ("exportAllCSVBtn", "venues.csv"),
        ("exportBeermapBtn", "beermap.html"),
        ("exportBeerstatsBtn", "beerstats.html"),
        ("exportEverythingBtn", "beer.zip"),
    ):
        with page.expect_download() as download:
            page.locator(f"#{button}").click()
        assert download.value.suggested_filename == filename
        content = Path(download.value.path()).read_bytes()
        if filename == "venues.json":
            assert json.loads(content) == cleaned
        elif filename == "venues.csv":
            assert content == parser.to_csv(cleaned).encode()
        elif filename == "beermap.html":
            assert inlined_json(content.decode(), "venue-data") == parser.to_geojson(
                venues, exclude_untappd_at_home=True
            )
        elif filename == "beerstats.html":
            assert inlined_json(content.decode(), "stats-data") == parser.to_dashboard_stats()
        else:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                assert sorted(archive.namelist()) == [
                    "beermap.html",
                    "beerstats.html",
                    "venues.csv",
                    "venues.json",
                ]
                assert archive.read("venues.csv") == parser.to_csv(cleaned).encode()
                assert inlined_json(
                    archive.read("beermap.html").decode(), "venue-data"
                ) == parser.to_geojson(venues, exclude_untappd_at_home=True)
                assert (
                    inlined_json(archive.read("beerstats.html").decode(), "stats-data")
                    == parser.to_dashboard_stats()
                )
    page.get_by_role("button", name="Process Another File").click()
    expect(page.locator("#uploadArea")).to_be_visible()
    page.locator("#fileInput").set_input_files(
        {
            "name": "another.json",
            "mimeType": "application/json",
            "buffer": json.dumps(checkins[:1]).encode(),
        }
    )
    expect(page.locator("#totalCheckins")).to_have_text("1")
    with page.expect_download() as download:
        page.locator("#exportBeerstatsBtn").click()
    assert (
        inlined_json(Path(download.value.path()).read_text(), "stats-data")
        == UntappdParser(data=checkins[:1]).to_dashboard_stats()
    )


def test_worker_keeps_ui_responsive_during_import_and_zip(page, site, checkins, tmp_path):
    origin, _ = site
    source = tmp_path / "large.json"
    source.write_text(json.dumps(checkins * 7000), encoding="utf-8")
    page.add_init_script("""(() => {
        window.busyFrames = 0;
        const frame = () => {
            if (document.getElementById('main-content')?.getAttribute('aria-busy') === 'true') {
                window.busyFrames++;
            }
            requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
    })()""")
    page.goto(f"{origin}/untappd.html")
    page.locator("#main-content").wait_for(state="visible", timeout=60000)
    page.locator("#fileInput").set_input_files(source)
    expect(page.locator("#totalCheckins")).to_have_text("42,000", timeout=30000)
    assert page.evaluate("window.busyFrames") >= 3
    page.evaluate("window.busyFrames = 0")
    with page.expect_download(timeout=30000) as download:
        page.locator("#exportEverythingBtn").click()
    assert download.value.suggested_filename == "beer.zip"
    assert page.evaluate("window.busyFrames") >= 3


def test_worker_reports_startup_failure(browser, site):
    origin, _ = site
    context = browser.new_context()
    context.route(
        "**/src/untappd_parser/pages.py",
        lambda route: route.fulfill(status=503, body="Unavailable"),
    )
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(f"{origin}/untappd.html")
        expect(page.locator("#loading-message")).to_have_text(
            "Could not start Python. Refresh the page to retry.", timeout=30000
        )
        expect(page.locator("#alertsError")).to_contain_text("HTTP 503")
        assert errors == []
    finally:
        context.close()
