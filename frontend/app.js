const API_BASE = "";

let currentStepSize = 1.0;
let driversEnabled = true;
let isMoving = false;

let latestPan = 0.0;
let latestTilt = 0.0;

let sseEventSource = null;
let httpPollingInterval = null;

// Telemetry state update handler (shared between SSE and HTTP polling)
function updateTelemetryData(data) {
    if (data.motors) {
        const m = data.motors;
        latestPan = m.pan;
        latestTilt = m.tilt;

        document.getElementById("valPan").textContent = `${m.pan.toFixed(2)}°`;
        document.getElementById("valTilt").textContent = `${m.tilt.toFixed(2)}°`;
        document.getElementById("valMode").textContent = m.mock_mode ? "Mock" : "Hardware";
        document.getElementById("valState").textContent = m.state;

        driversEnabled = m.drivers_enabled !== false;
        document.getElementById("valDrivers").textContent = driversEnabled ? "ON" : "OFF";

        const driverBtn = document.getElementById("btnDriverToggle");
        if (driverBtn) {
            driverBtn.textContent = driversEnabled ? "Disable Drivers" : "Enable Drivers";
        }

        const badge = document.getElementById("statusBadge");
        const statusText = document.getElementById("statusText");
        badge.classList.add("connected");
        statusText.textContent = m.mock_mode ? "MOTORS (MOCK)" : "MOTORS OK";
    }

    if (data.camera) {
        const c = data.camera;
        document.getElementById("valCameraModel").textContent = c.model || "Canon DSLR";
        document.getElementById("valCameraIso").textContent = c.iso || "--";
        document.getElementById("valCameraShutter").textContent = c.shutter_speed || "--";

        const badge = document.getElementById("cameraStatusBadge");
        const statusText = document.getElementById("cameraStatusText");
        badge.classList.add("connected");
        statusText.textContent = c.mock_mode ? "CAMERA (MOCK)" : "CAMERA OK";

        if (c.has_latest_photo) {
            updatePreviewImage();
        }
    }

    if (data.timelapse) {
        const t = data.timelapse;
        document.getElementById("tlValState").textContent = t.state;
        document.getElementById("tlValShot").textContent = `${t.current_shot} / ${t.total_shots}`;
        document.getElementById("tlValPct").textContent = `${t.progress_pct}%`;
        document.getElementById("tlValElapsed").textContent = `${t.elapsed_time_s}s`;
        document.getElementById("tlValEta").textContent = `${t.estimated_eta_s}s`;

        const progressBar = document.getElementById("tlProgressBar");
        if (progressBar) {
            progressBar.style.width = `${t.progress_pct}%`;
        }

        const btnPause = document.getElementById("btnTlPause");
        const btnResume = document.getElementById("btnTlResume");

        if (t.state === "RUNNING") {
            btnPause.classList.remove("hidden");
            btnResume.classList.add("hidden");
        } else if (t.state === "PAUSED") {
            btnPause.classList.add("hidden");
            btnResume.classList.remove("hidden");
        }
    }
}

// Server-Sent Events (SSE) Listener with Automatic HTTP Polling Fallback
function initSSE() {
    if (window.EventSource) {
        try {
            console.log("Connecting to SSE event stream...");
            sseEventSource = new EventSource(`${API_BASE}/api/events`);

            sseEventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    if (!isMoving) {
                        updateTelemetryData(data);
                    }
                } catch (e) {
                    console.error("Error parsing SSE event:", e);
                }
            };

            sseEventSource.onerror = (err) => {
                console.warn("SSE stream disconnected or failed. Falling back to HTTP polling...", err);
                if (sseEventSource) {
                    sseEventSource.close();
                    sseEventSource = null;
                }
                startHTTPPollingFallback();
            };
        } catch (e) {
            console.warn("Failed to initialize SSE. Starting HTTP polling fallback...", e);
            startHTTPPollingFallback();
        }
    } else {
        console.warn("EventSource not supported by browser. Starting HTTP polling...");
        startHTTPPollingFallback();
    }
}

function startHTTPPollingFallback() {
    if (!httpPollingInterval) {
        fetchStatus();
        httpPollingInterval = setInterval(fetchStatus, 1000);
    }
}

// HTTP Polling Fallback Implementation
async function fetchStatus() {
    if (isMoving) return;

    try {
        const motorRes = await fetch(`${API_BASE}/api/motors/status`);
        const cameraRes = await fetch(`${API_BASE}/api/camera/status`);
        const tlRes = await fetch(`${API_BASE}/api/timelapse/status`);

        const motors = motorRes.ok ? await motorRes.json() : null;
        const camera = cameraRes.ok ? await cameraRes.json() : null;
        const timelapse = tlRes.ok ? await tlRes.json() : null;

        updateTelemetryData({ motors, camera, timelapse });
    } catch (err) {
        console.error("HTTP Polling fallback error:", err);
    }
}

function updatePreviewImage() {
    const img = document.getElementById("previewImg");
    const placeholder = document.getElementById("previewPlaceholder");
    if (img && placeholder) {
        img.src = `${API_BASE}/api/camera/preview/latest?t=${new Date().getTime()}`;
        img.classList.remove("hidden");
        placeholder.classList.add("hidden");
    }
}

// Keyframe Helpers
function setKeyframeA() {
    document.getElementById("inputStartPan").value = latestPan.toFixed(1);
    document.getElementById("inputStartTilt").value = latestTilt.toFixed(1);
}

function setKeyframeB() {
    document.getElementById("inputEndPan").value = latestPan.toFixed(1);
    document.getElementById("inputEndTilt").value = latestTilt.toFixed(1);
}

// Time-lapse Controls
async function startTimelapse() {
    const easingSelect = document.getElementById("selectEasing");
    const easingVal = easingSelect ? easingSelect.value : "ease_in_out";

    const config = {
        start_pan: parseFloat(document.getElementById("inputStartPan").value) || 0.0,
        start_tilt: parseFloat(document.getElementById("inputStartTilt").value) || 0.0,
        end_pan: parseFloat(document.getElementById("inputEndPan").value) || 15.0,
        end_tilt: parseFloat(document.getElementById("inputEndTilt").value) || 0.0,
        total_shots: parseInt(document.getElementById("inputTotalShots").value) || 10,
        interval_s: parseFloat(document.getElementById("inputInterval").value) || 5.0,
        settle_time_s: 0.5,
        capture_photo: true,
        easing: easingVal
    };

    try {
        const res = await fetch(`${API_BASE}/api/timelapse/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(config)
        });
        const data = await res.json();
        if (data.status !== "OK") {
            alert(`Start failed: ${data.message}`);
        }
    } catch (err) {
        console.error("Start timelapse failed:", err);
    }
}

async function pauseTimelapse() {
    try {
        await fetch(`${API_BASE}/api/timelapse/pause`, { method: "POST" });
    } catch (err) {
        console.error("Pause timelapse failed:", err);
    }
}

async function resumeTimelapse() {
    try {
        await fetch(`${API_BASE}/api/timelapse/resume`, { method: "POST" });
    } catch (err) {
        console.error("Resume timelapse failed:", err);
    }
}

async function cancelTimelapse() {
    try {
        await fetch(`${API_BASE}/api/timelapse/cancel`, { method: "POST" });
    } catch (err) {
        console.error("Cancel timelapse failed:", err);
    }
}

async function setCameraConfig(param, value) {
    try {
        await fetch(`${API_BASE}/api/camera/config`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ param: param, value: value })
        });
    } catch (err) {
        console.error("Set camera config failed:", err);
    }
}

async function triggerTestShot() {
    const placeholder = document.getElementById("previewPlaceholder");
    if (placeholder) placeholder.textContent = "Capturing photo & downloading...";

    try {
        const res = await fetch(`${API_BASE}/api/camera/trigger`, { method: "POST" });
        const data = await res.json();
        if (data.status === "OK") {
            updatePreviewImage();
        } else {
            alert(`Capture failed: ${data.message || "Unknown error"}`);
            if (placeholder) placeholder.textContent = "Capture failed";
        }
    } catch (err) {
        console.error("Trigger test shot failed:", err);
        if (placeholder) placeholder.textContent = "Trigger request error";
    }
}

function setStepSize(step) {
    currentStepSize = step;
    document.querySelectorAll(".segment").forEach(btn => {
        if (parseFloat(btn.dataset.step) === step) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
}

function getStepSize() {
    return currentStepSize;
}

async function moveRelative(panDelta, tiltDelta) {
    isMoving = true;
    document.getElementById("valState").textContent = "MOVING";
    try {
        await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan: panDelta, tilt: tiltDelta, relative: true })
        });
    } catch (err) {
        console.error("Move relative failed:", err);
    } finally {
        isMoving = false;
    }
}

async function moveAbsolute(pan, tilt) {
    isMoving = true;
    document.getElementById("valState").textContent = "MOVING";
    try {
        await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan: pan, tilt: tilt, relative: false })
        });
    } catch (err) {
        console.error("Move absolute failed:", err);
    } finally {
        isMoving = false;
    }
}

async function toggleDrivers() {
    try {
        await fetch(`${API_BASE}/api/motors/drivers`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enable: !driversEnabled })
        });
    } catch (err) {
        console.error("Toggle drivers failed:", err);
    }
}

async function stopMotors() {
    try {
        await fetch(`${API_BASE}/api/motors/stop`, { method: "POST" });
    } catch (err) {
        console.error("Stop request failed:", err);
    }
}

// Initialize SSE with HTTP Polling Fallback
initSSE();
