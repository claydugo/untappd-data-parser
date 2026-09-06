import heapq
import html
import io
import json
import zipfile

from js import Blob, FileReader, Object, console
from js import self as window
from pyodide.ffi import create_once_callable, create_proxy, to_js

from untappd_parser import UntappdParser
from untappd_parser.pages import render_beermap, render_beerstats


class AppState:
    def __init__(self):
        self.parser = None
        self.processed_venues = None
        self.venues_geojson = None
        self.dashboard_stats = None
        self.cleaned_data = None
        self.alert_timer = None
        self.options = {}

    def reset(self):
        self.parser = None
        self.processed_venues = None
        self.venues_geojson = None
        self.dashboard_stats = None
        self.cleaned_data = None

    def has_data(self):
        return self.cleaned_data is not None


app_state = AppState()


def publish(message):
    window.postMessage(to_js(message, dict_converter=Object.fromEntries))


# setTimeout needs a persistent proxy; a bare lambda is destroyed before the timer fires.
_dismiss_alert = create_proxy(lambda: publish({"type": "dismiss-alert"}))


def show_alert(message, alert_type="info"):
    allowed_types = {"info", "success", "error"}
    alert_class = alert_type if alert_type in allowed_types else "info"

    publish({"type": "alert", "message": str(message), "level": alert_class})

    if app_state.alert_timer is not None:
        window.clearTimeout(app_state.alert_timer)
        app_state.alert_timer = None

    # Errors stay until replaced; info/success auto-dismiss.
    if alert_class != "error":
        app_state.alert_timer = window.setTimeout(_dismiss_alert, 5000)


def escape_html(text):
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def data_to_csv(data):
    if not data:
        return ""

    try:
        # Rows can have heterogeneous key sets; take the union so DictWriter never raises.
        return UntappdParser.to_csv(data)
    except Exception as e:
        console.error(f"CSV generation error: {e!s}")
        show_alert("Error generating CSV file", "error")
        return ""


def download_file(content, filename, mime_type="text/plain"):
    # A bare dict reaches JS as a PyProxy and the Blob type reads back as "dict".
    # bytes needs the same treatment to arrive as a Uint8Array rather than a proxy.
    payload = to_js(content) if isinstance(content, bytes) else content
    blob = Blob.new([payload], to_js({"type": mime_type}, dict_converter=Object.fromEntries))
    publish({"type": "download", "blob": blob, "filename": filename})


def process_file(file_content):
    try:
        data = json.loads(file_content)

        if not isinstance(data, list):
            raise ValueError("Data must be an array of check-ins")
        if len(data) == 0:
            raise ValueError("No check-ins found in file")

        required_fields = ["venue_name", "venue_lat", "venue_lng", "created_at"]
        sample_item = data[0]
        missing_fields = [field for field in required_fields if field not in sample_item]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        human_keys = app_state.options["humanKeys"]
        strip_backend = app_state.options["stripBackend"]
        fancy_dates = app_state.options["fancyDates"]

        app_state.parser = UntappdParser(data=data)
        app_state.processed_venues = app_state.parser.get_unique_entries("venue")
        # clean_data mutates the venue dicts in place; capture the GeoJSON first.
        app_state.venues_geojson = app_state.parser.to_geojson(
            app_state.processed_venues,
            exclude_untappd_at_home=app_state.options["excludeUntappdAtHome"],
        )
        app_state.cleaned_data = app_state.parser.clean_data(
            app_state.processed_venues,
            strip_backend=strip_backend,
            fancy_dates=fancy_dates,
            human_keys=human_keys,
        )

        update_results()

        show_alert(f"Successfully processed {len(data)} check-ins!", "success")

    except Exception as e:
        app_state.reset()
        publish({"type": "reset"})
        show_alert(f"Error: {e!s}", "error")
        console.error(f"Processing error: {e!s}")
    finally:
        publish({"type": "busy", "value": False})


def update_results():
    if not app_state.has_data():
        return

    stats = app_state.parser.get_stats(unique_entries=app_state.processed_venues)

    distribution = app_state.parser.get_visit_distribution(app_state.cleaned_data)

    def field(venue, key, default=None):
        # Keys vary with the humanKeys/fancyDates checkboxes: humanized name first, then raw.
        for candidate in (key.replace("_", " ").title(), key):
            value = venue.get(candidate)
            if value is not None:
                return value
        return default

    top_10 = heapq.nlargest(
        10,
        app_state.cleaned_data,
        key=lambda venue: venue.get("Total Venue Checkins", venue.get("total_venue_checkins", 0)),
    )

    preview_html = ""
    for venue in top_10:
        visits = field(venue, "total_venue_checkins", default=0)
        badge_class = (
            "badge-primary" if visits == 1 else "badge-warning" if visits <= 4 else "badge-success"
        )

        venue_name = escape_html(field(venue, "venue_name", default="(No venue)"))
        lat = field(venue, "venue_lat")
        lng = field(venue, "venue_lng")

        if lat is not None and lng is not None:
            try:
                location = f"{float(lat):.4f}, {float(lng):.4f}"
            except (ValueError, TypeError):
                location = "Invalid coordinates"
        else:
            location = "No location"

        first_checkin = escape_html(field(venue, "first_checkin", default="N/A"))
        last_checkin = escape_html(field(venue, "last_checkin", default=""))

        preview_html += f"""
        <div class="venue-item">
            <div class="venue-name">
                {venue_name}
                <span class="badge {badge_class}">{visits} visits</span>
            </div>
            <div class="venue-details">
                📍 {location}<br>
                🗓️ First: {first_checkin}
                {f"<br>🗓️ Last: {last_checkin}" if last_checkin else ""}
            </div>
        </div>
        """

    publish(
        {
            "type": "results",
            "statistics": {
                "totalCheckins": f"{stats['total_checkins']:,}",
                "uniqueVenues": f"{stats['unique_venues']:,}",
                "duplicates": f"{stats['duplicates']:,}",
                "singleVisit": f"{len(distribution['1_visit']):,}",
                "twoToFour": f"{len(distribution['2-4_visits']):,}",
                "fivePlus": f"{len(distribution['5+_visits']):,}",
            },
            "preview": preview_html,
            "split": app_state.options["splitByVisits"],
        }
    )


def process_selected_file(file):
    if not file.name.lower().endswith(".json"):
        show_alert("Please upload a JSON file", "error")
        publish({"type": "busy", "value": False})
        return False

    if file.size > 50 * 1024 * 1024:  # 50MB limit
        show_alert("File size exceeds 50MB limit", "error")
        publish({"type": "busy", "value": False})
        return False

    publish({"type": "busy", "value": True})

    reader = FileReader.new()

    def on_load(e):
        process_file(e.target.result.to_bytes())

    def on_error(e):
        publish({"type": "busy", "value": False})
        show_alert("Could not read the file. Please try again.", "error")

    load_proxy = create_proxy(on_load)
    error_proxy = create_proxy(on_error)

    def on_loadend(e):
        # loadend fires after load/error/abort; free the handler proxies here.
        reader.onload = None
        reader.onerror = None
        reader.onabort = None
        load_proxy.destroy()
        error_proxy.destroy()

    reader.onload = load_proxy
    reader.onerror = error_proxy
    reader.onabort = error_proxy
    reader.onloadend = create_once_callable(on_loadend)
    reader.readAsArrayBuffer(file)
    return True


def handle_file(event):
    app_state.reset()
    if not process_selected_file(event.data.file):
        # Clear the rejected file so re-selecting the same one fires change again.
        publish({"type": "reset"})


def export_all(event):
    if app_state.has_data():
        content = json.dumps(app_state.cleaned_data, indent=2, ensure_ascii=False)
        download_file(content, "venues.json", "application/json")


def export_all_csv(event):
    if app_state.has_data():
        csv_content = data_to_csv(app_state.cleaned_data)
        download_file(csv_content, "venues.csv", "text/csv")


def export_beermap(event):
    # No sibling link: this download lands on its own, so the link would be dead.
    if app_state.has_data():
        download_file(
            render_beermap(app_state.venues_geojson),
            "beermap.html",
            "text/html",
        )


def export_beerstats(event):
    if app_state.has_data():
        if app_state.dashboard_stats is None:
            app_state.dashboard_stats = app_state.parser.to_dashboard_stats()
        download_file(
            render_beerstats(app_state.dashboard_stats),
            "beerstats.html",
            "text/html",
        )


def export_everything(event):
    if not app_state.has_data():
        return
    split_by_visits = app_state.options["splitByVisits"]
    if app_state.dashboard_stats is None:
        app_state.dashboard_stats = app_state.parser.to_dashboard_stats()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as bundle:
        bundle.writestr(
            "beermap.html", render_beermap(app_state.venues_geojson, link_to_stats=True)
        )
        bundle.writestr(
            "beerstats.html",
            render_beerstats(app_state.dashboard_stats, link_to_map=True),
        )
        bundle.writestr(
            "venues.json", json.dumps(app_state.cleaned_data, indent=2, ensure_ascii=False)
        )
        if split_by_visits:
            distribution = app_state.parser.get_visit_distribution(app_state.cleaned_data)
            for bucket, filename in (
                ("1_visit", "venues-1-visit.csv"),
                ("2-4_visits", "venues-2-4-visits.csv"),
                ("5+_visits", "venues-5-plus-visits.csv"),
            ):
                if distribution[bucket]:
                    bundle.writestr(filename, data_to_csv(distribution[bucket]))
        else:
            bundle.writestr("venues.csv", data_to_csv(app_state.cleaned_data))
    download_file(archive.getvalue(), "beer.zip", "application/zip")
    show_alert("Exported everything as beer.zip", "success")


def export_1_visit(event):
    if not app_state.has_data():
        return
    distribution = app_state.parser.get_visit_distribution(app_state.cleaned_data)
    data = distribution["1_visit"]
    if data:
        csv_content = data_to_csv(data)
        download_file(csv_content, "venues-1-visit.csv", "text/csv")
        show_alert(f"Exported {len(data)} venues with 1 visit", "success")
    else:
        show_alert("No venues with 1 visit to export", "info")


def export_2_4_visits(event):
    if not app_state.has_data():
        return
    distribution = app_state.parser.get_visit_distribution(app_state.cleaned_data)
    data = distribution["2-4_visits"]
    if data:
        csv_content = data_to_csv(data)
        download_file(csv_content, "venues-2-4-visits.csv", "text/csv")
        show_alert(f"Exported {len(data)} venues with 2-4 visits", "success")
    else:
        show_alert("No venues with 2-4 visits to export", "info")


def export_5_plus_visits(event):
    if not app_state.has_data():
        return
    distribution = app_state.parser.get_visit_distribution(app_state.cleaned_data)
    data = distribution["5+_visits"]
    if data:
        csv_content = data_to_csv(data)
        download_file(csv_content, "venues-5-plus-visits.csv", "text/csv")
        show_alert(f"Exported {len(data)} venues with 5+ visits", "success")
    else:
        show_alert("No venues with 5+ visits to export", "info")


def on_split_change(event):
    if app_state.has_data():
        update_results()


def reset_for_new_file():
    app_state.reset()
    if app_state.alert_timer is not None:
        window.clearTimeout(app_state.alert_timer)
        app_state.alert_timer = None
    publish({"type": "reset"})


def handle_message(event):
    command = event.data.command
    if command == "process":
        app_state.options = event.data.options.to_py()
        handle_file(event)
    elif command == "reset":
        reset_for_new_file()
    elif command == "split":
        app_state.options["splitByVisits"] = event.data.value
        on_split_change(event)
    elif command == "export":
        try:
            {
                "json": export_all,
                "csv": export_all_csv,
                "map": export_beermap,
                "stats": export_beerstats,
                "zip": export_everything,
                "single": export_1_visit,
                "few": export_2_4_visits,
                "many": export_5_plus_visits,
            }[event.data.artifact](event)
        except Exception as error:
            show_alert(f"Export failed: {error}", "error")
        finally:
            publish({"type": "busy", "value": False})


def init_app():
    """Initialize the web application by setting up all event listeners"""
    window.addEventListener("message", create_proxy(handle_message))
    publish({"type": "ready"})
