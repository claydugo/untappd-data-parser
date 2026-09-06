const fileInput = document.getElementById("fileInput");
const uploadArea = document.getElementById("uploadArea");
const results = document.getElementById("results");
const processingOptions = document.getElementById("processing-options");
let busy = false;

function setBusy(value) {
	busy = value;
	document.getElementById("loading").classList.toggle("active", value);
	document.getElementById("main-content").setAttribute("aria-busy", String(value));
	uploadArea.setAttribute("aria-disabled", String(value));
	for (const control of document.querySelectorAll("#main-content button, #processing-options input, #fileInput")) {
		control.disabled = value;
	}
}

function showError(message) {
	const alert = document.createElement("div");
	alert.className = "alert alert-error";
	alert.textContent = message;
	document.getElementById("alertsError").replaceChildren(alert);
	document.getElementById("alertsStatus").replaceChildren();
}

const workerAddress = URL.createObjectURL(new Blob([
	document.getElementById("parser-worker").textContent,
], { type: "text/javascript" }));
let worker;
try {
	worker = new Worker(workerAddress, { type: "module" });
	worker.addEventListener("error", () => {
		setBusy(false);
		showError("The Python worker stopped. Refresh the page to restart it.");
		document.getElementById("loading-message").textContent = "Could not start Python. Refresh the page to retry.";
	});
	worker.addEventListener("message", ({ data }) => {
		if (data.type === "ready") {
			document.getElementById("loading-message").classList.add("hidden");
			document.getElementById("main-content").classList.remove("hidden");
			URL.revokeObjectURL(workerAddress);
		} else if (data.type === "startup-error") {
			document.getElementById("loading-message").textContent = "Could not start Python. Refresh the page to retry.";
			showError(data.message);
		} else if (data.type === "busy") {
			setBusy(data.value);
		} else if (data.type === "reset") {
			uploadArea.style.display = "block";
			processingOptions.style.display = "block";
			results.classList.remove("active");
			fileInput.value = "";
		} else if (data.type === "results") {
			for (const [identifier, value] of Object.entries(data.statistics)) {
				document.getElementById(identifier).textContent = value;
			}
			document.getElementById("venuePreview").innerHTML = data.preview;
			document.getElementById("split-buttons").style.display = data.split ? "contents" : "none";
			for (const identifier of ["singleVisit", "twoToFour", "fivePlus"]) {
				document.getElementById(identifier).parentElement.parentElement.style.display = data.split ? "block" : "none";
			}
			uploadArea.style.display = "none";
			processingOptions.style.display = "none";
			results.classList.add("active");
		} else if (data.type === "alert") {
			if (data.level === "error") {
				showError(data.message);
			} else {
				const alert = document.createElement("div");
				alert.className = `alert alert-${data.level}`;
				alert.textContent = data.message;
				document.getElementById("alertsStatus").replaceChildren(alert);
				document.getElementById("alertsError").replaceChildren();
			}
		} else if (data.type === "dismiss-alert") {
			document.getElementById("alertsStatus").replaceChildren();
		} else if (data.type === "download") {
			const address = URL.createObjectURL(data.blob);
			const link = document.createElement("a");
			link.href = address;
			link.download = data.filename;
			link.click();
			setTimeout(() => URL.revokeObjectURL(address), 0);
		}
	});
	worker.postMessage({
		baseUrl: document.baseURI,
		integrity: JSON.parse(document.querySelector('script[type="importmap"]').textContent).integrity,
	});
} catch (error) {
	URL.revokeObjectURL(workerAddress);
	document.getElementById("loading-message").textContent = "Could not start Python. Refresh the page to retry.";
	showError(error.message);
}

fileInput.addEventListener("change", () => {
	if (busy || !worker || !fileInput.files.length) return;
	setBusy(true);
	results.classList.remove("active");
	worker.postMessage({
		command: "process",
		file: fileInput.files[0],
		options: Object.fromEntries(Array.from(processingOptions.querySelectorAll("input"), input => [input.id, input.checked])),
	});
});
uploadArea.addEventListener("click", (event) => {
	if (!busy && event.target !== fileInput) fileInput.click();
});
uploadArea.addEventListener("keydown", (event) => {
	if (!busy && (event.key === "Enter" || event.key === " ")) {
		event.preventDefault();
		fileInput.click();
	}
});
uploadArea.addEventListener("dragover", (event) => {
	event.preventDefault();
	if (!busy) uploadArea.classList.add("dragover");
});
uploadArea.addEventListener("dragleave", () => uploadArea.classList.remove("dragover"));
uploadArea.addEventListener("drop", (event) => {
	event.preventDefault();
	uploadArea.classList.remove("dragover");
	if (busy || !event.dataTransfer.files.length) return;
	fileInput.files = event.dataTransfer.files;
	fileInput.dispatchEvent(new Event("change"));
});
for (const [identifier, artifact] of Object.entries({
	exportAllBtn: "json",
	exportAllCSVBtn: "csv",
	exportBeermapBtn: "map",
	exportBeerstatsBtn: "stats",
	exportEverythingBtn: "zip",
	export1Btn: "single",
	export24Btn: "few",
	export5Btn: "many",
})) {
	document.getElementById(identifier).addEventListener("click", () => {
		if (busy || !worker) return;
		setBusy(true);
		worker.postMessage({ command: "export", artifact });
	});
}
window.resetForNewFile = () => {
	if (busy || !worker) return;
	document.getElementById("alertsStatus").replaceChildren();
	document.getElementById("alertsError").replaceChildren();
	worker.postMessage({ command: "reset" });
};
document.getElementById("splitByVisits").addEventListener("change", (event) => {
	if (!busy && worker) worker.postMessage({ command: "split", value: event.target.checked });
});
