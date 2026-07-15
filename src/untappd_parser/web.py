import csv
import html
import io
import json

from js import URL, Blob, FileReader, console, document, window
from pyodide.ffi import create_once_callable, create_proxy

from untappd_parser import UntappdParser


class AppState:
    def __init__(self):
        self.parser = None
        self.processed_venues = None
        self.cleaned_data = None
        self.alert_timer = None

    def reset(self):
        self.parser = None
        self.processed_venues = None
        self.cleaned_data = None

    def has_data(self):
        return self.cleaned_data is not None


app_state = AppState()


# setTimeout needs a persistent proxy; a bare lambda is destroyed before the timer fires.
_dismiss_alert = create_proxy(lambda: document.getElementById("alertsStatus").replaceChildren())


def show_alert(message, alert_type="info"):
    allowed_types = {"info", "success", "error"}
    alert_class = alert_type if alert_type in allowed_types else "info"

    error_region = document.getElementById("alertsError")
    status_region = document.getElementById("alertsStatus")
    target = error_region if alert_class == "error" else status_region
    other = status_region if alert_class == "error" else error_region

    alert_element = document.createElement("div")
    alert_element.classList.add("alert", f"alert-{alert_class}")
    alert_element.textContent = str(message)

    other.replaceChildren()
    target.replaceChildren(alert_element)

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
        output = io.StringIO()
        # Rows can have heterogeneous key sets; take the union so DictWriter never raises.
        fieldnames = list(dict.fromkeys(key for entry in data for key in entry))
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        return output.getvalue()
    except Exception as e:
        console.error(f"CSV generation error: {e!s}")
        show_alert("Error generating CSV file", "error")
        return ""


def download_file(content, filename, mime_type="text/plain"):
    blob = Blob.new([content], {"type": mime_type})
    url = URL.createObjectURL(blob)

    link = document.createElement("a")
    link.href = url
    link.download = filename
    link.click()

    URL.revokeObjectURL(url)


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

        human_keys = document.getElementById("humanKeys").checked
        strip_backend = document.getElementById("stripBackend").checked
        fancy_dates = document.getElementById("fancyDates").checked

        app_state.parser = UntappdParser(data=data)
        app_state.processed_venues = app_state.parser.get_unique_entries("venue")
        app_state.cleaned_data = app_state.parser.clean_data(
            app_state.processed_venues,
            strip_backend=strip_backend,
            fancy_dates=fancy_dates,
            human_keys=human_keys,
        )

        update_results()

        document.getElementById("uploadArea").style.display = "none"
        document.getElementById("processing-options").style.display = "none"

        document.getElementById("results").classList.add("active")
        document.getElementById("loading").classList.remove("active")

        show_alert(f"Successfully processed {len(data)} check-ins!", "success")

    except Exception as e:
        app_state.reset()
        document.getElementById("loading").classList.remove("active")
        show_alert(f"Error: {e!s}", "error")
        console.error(f"Processing error: {e!s}")


def update_results():
    if not app_state.has_data():
        return

    stats = app_state.parser.get_stats(unique_entries=app_state.processed_venues)

    document.getElementById("totalCheckins").textContent = f"{stats['total_checkins']:,}"
    document.getElementById("uniqueVenues").textContent = f"{stats['unique_venues']:,}"
    document.getElementById("duplicates").textContent = f"{stats['duplicates']:,}"

    split_by_visits = document.getElementById("splitByVisits").checked
    split_buttons = document.getElementById("split-buttons")
    if split_by_visits:
        split_buttons.style.display = "contents"
        distribution = app_state.parser.get_visit_distribution(app_state.cleaned_data)
        document.getElementById("singleVisit").textContent = f"{len(distribution['1_visit']):,}"
        document.getElementById("twoToFour").textContent = f"{len(distribution['2-4_visits']):,}"
        document.getElementById("fivePlus").textContent = f"{len(distribution['5+_visits']):,}"
        document.getElementById("singleVisit").parentElement.parentElement.style.display = "block"
        document.getElementById("twoToFour").parentElement.parentElement.style.display = "block"
        document.getElementById("fivePlus").parentElement.parentElement.style.display = "block"
    else:
        split_buttons.style.display = "none"
        document.getElementById("singleVisit").parentElement.parentElement.style.display = "none"
        document.getElementById("twoToFour").parentElement.parentElement.style.display = "none"
        document.getElementById("fivePlus").parentElement.parentElement.style.display = "none"

    def field(venue, key, default=None):
        # Keys vary with the humanKeys/fancyDates checkboxes: humanized name first, then raw.
        for candidate in (key.replace("_", " ").title(), key):
            value = venue.get(candidate)
            if value is not None:
                return value
        return default

    sorted_venues = sorted(
        app_state.cleaned_data,
        key=lambda x: field(x, "total_venue_checkins", default=0),
        reverse=True,
    )
    top_10 = sorted_venues[:10]

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

    document.getElementById("venuePreview").innerHTML = preview_html


def process_selected_file(file):
    if not file.name.lower().endswith(".json"):
        show_alert("Please upload a JSON file", "error")
        return False

    if file.size > 50 * 1024 * 1024:  # 50MB limit
        show_alert("File size exceeds 50MB limit", "error")
        return False

    document.getElementById("loading").classList.add("active")
    document.getElementById("results").classList.remove("active")

    reader = FileReader.new()

    def on_load(e):
        process_file(e.target.result)

    def on_error(e):
        document.getElementById("loading").classList.remove("active")
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
    reader.readAsText(file)
    return True


def handle_file(event):
    file_input = document.getElementById("fileInput")
    files = file_input.files
    if files.length > 0 and not process_selected_file(files.item(0)):
        # Clear the rejected file so re-selecting the same one fires change again.
        file_input.value = ""


def dragover(e):
    e.preventDefault()
    document.getElementById("uploadArea").classList.add("dragover")


def dragleave(e):
    e.preventDefault()
    document.getElementById("uploadArea").classList.remove("dragover")


def drop(e):
    e.preventDefault()
    document.getElementById("uploadArea").classList.remove("dragover")

    files = e.dataTransfer.files
    if files.length > 0 and process_selected_file(files.item(0)):
        document.getElementById("fileInput").files = files


def export_all(event):
    if app_state.has_data():
        content = json.dumps(app_state.cleaned_data, indent=2)
        download_file(content, "venues_all.json", "application/json")


def export_all_csv(event):
    if app_state.has_data():
        csv_content = data_to_csv(app_state.cleaned_data)
        download_file(csv_content, "venues_all.csv", "text/csv")


def export_1_visit(event):
    if not app_state.has_data():
        return
    distribution = app_state.parser.get_visit_distribution(app_state.cleaned_data)
    data = distribution["1_visit"]
    if data:
        csv_content = data_to_csv(data)
        download_file(csv_content, "venues_1_visit.csv", "text/csv")
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
        download_file(csv_content, "venues_2-4_visits.csv", "text/csv")
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
        download_file(csv_content, "venues_5+_visits.csv", "text/csv")
        show_alert(f"Exported {len(data)} venues with 5+ visits", "success")
    else:
        show_alert("No venues with 5+ visits to export", "info")


def on_split_change(event):
    if app_state.has_data():
        update_results()


def reset_for_new_file():
    app_state.reset()
    document.getElementById("uploadArea").style.display = "block"
    document.getElementById("processing-options").style.display = "block"
    document.getElementById("results").classList.remove("active")
    document.getElementById("fileInput").value = ""
    document.getElementById("alertsStatus").replaceChildren()
    document.getElementById("alertsError").replaceChildren()


def init_app():
    """Initialize the web application by setting up all event listeners"""
    file_input = document.getElementById("fileInput")
    file_input.addEventListener("change", create_proxy(handle_file))

    upload_area = document.getElementById("uploadArea")
    upload_area.onclick = lambda e: file_input.click()

    def upload_area_keydown(e):
        if e.key in ("Enter", " "):
            e.preventDefault()
            file_input.click()

    upload_area.addEventListener("keydown", create_proxy(upload_area_keydown))

    upload_area.addEventListener("dragover", create_proxy(dragover))
    upload_area.addEventListener("dragleave", create_proxy(dragleave))
    upload_area.addEventListener("drop", create_proxy(drop))

    document.getElementById("exportAllBtn").addEventListener("click", create_proxy(export_all))
    document.getElementById("exportAllCSVBtn").addEventListener(
        "click", create_proxy(export_all_csv)
    )
    document.getElementById("export1Btn").addEventListener("click", create_proxy(export_1_visit))
    document.getElementById("export24Btn").addEventListener(
        "click", create_proxy(export_2_4_visits)
    )
    document.getElementById("export5Btn").addEventListener(
        "click", create_proxy(export_5_plus_visits)
    )

    window.resetForNewFile = create_proxy(reset_for_new_file)

    document.getElementById("splitByVisits").addEventListener(
        "change", create_proxy(on_split_change)
    )

    document.getElementById("loading-message").classList.add("hidden")
    document.getElementById("main-content").classList.remove("hidden")

    console.log("Pyodide initialized - using untappd_parser package!")
