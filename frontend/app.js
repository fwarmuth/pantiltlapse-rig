const API_BASE = "";

let currentStepSize = 1.0;
let driversEnabled = true;
let isMoving = false;

// Motor & Camera Telemetry Polling
async function fetchStatus() {
    if (isMoving) return;

    try {
        const res = await fetch(`${API_BASE}/api/motors/status`);
        if (!res.ok) throw new Error("Motor API Offline");
        const data = await res.json();
        
        document.getElementById("valPan").textContent = `${data.pan.toFixed(2)}°`;
        document.getElementById("valTilt").textContent = `${data.tilt.toFixed(2)}°`;
        document.getElementById("valMode").textContent = data.mock_mode ? "Mock" : "Hardware";
        document.getElementById("valState").textContent = data.state;
        
        driversEnabled = data.drivers_enabled !== false;
        document.getElementById("valDrivers").textContent = driversEnabled ? "ON" : "OFF";
        
        const driverBtn = document.getElementById("btnDriverToggle");
        if (driverBtn) {
            driverBtn.textContent = driversEnabled ? "Disable Drivers" : "Enable Drivers";
        }
        
        const badge = document.getElementById("statusBadge");
        const statusText = document.getElementById("statusText");
        badge.classList.add("connected");
        statusText.textContent = data.mock_mode ? "MOTORS (MOCK)" : "MOTORS OK";
    } catch (err) {
        const badge = document.getElementById("statusBadge");
        const statusText = document.getElementById("statusText");
        badge.classList.remove("connected");
        statusText.textContent = "MOTORS OFF";
    }

    // Fetch Camera Status
    await fetchCameraStatus();
}

async function fetchCameraStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/camera/status`);
        if (!res.ok) throw new Error("Camera API Offline");
        const data = await res.json();

        document.getElementById("valCameraModel").textContent = data.model || "Canon DSLR";
        document.getElementById("valCameraIso").textContent = data.iso || "--";
        document.getElementById("valCameraShutter").textContent = data.shutter_speed || "--";

        const badge = document.getElementById("cameraStatusBadge");
        const statusText = document.getElementById("cameraStatusText");
        badge.classList.add("connected");
        statusText.textContent = data.mock_mode ? "CAMERA (MOCK)" : "CAMERA OK";

        if (data.has_latest_photo) {
            updatePreviewImage();
        }
    } catch (err) {
        const badge = document.getElementById("cameraStatusBadge");
        const statusText = document.getElementById("cameraStatusText");
        badge.classList.remove("connected");
        statusText.textContent = "CAMERA OFF";
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

async function setCameraConfig(param, value) {
    try {
        await fetch(`${API_BASE}/api/camera/config`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ param: param, value: value })
        });
        fetchCameraStatus();
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

async function executeMotionShotStep(panDelta, tiltDelta) {
    isMoving = true;
    document.getElementById("valState").textContent = "STEPPING";
    const placeholder = document.getElementById("previewPlaceholder");
    if (placeholder) placeholder.textContent = "Executing Move -> Settle -> Capture...";

    try {
        const res = await fetch(`${API_BASE}/api/sequence/step`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                pan: panDelta,
                tilt: tiltDelta,
                relative: true,
                pause_s: 0.5,
                capture: true
            })
        });
        const data = await res.json();
        if (data.status === "OK") {
            updatePreviewImage();
        } else {
            alert(`Step failed: ${data.message || "Unknown error"}`);
        }
    } catch (err) {
        console.error("Step execution failed:", err);
    } finally {
        isMoving = false;
        fetchStatus();
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
        fetchStatus();
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
        fetchStatus();
    }
}

async function toggleDrivers() {
    try {
        await fetch(`${API_BASE}/api/motors/drivers`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enable: !driversEnabled })
        });
        fetchStatus();
    } catch (err) {
        console.error("Toggle drivers failed:", err);
    }
}

async function stopMotors() {
    try {
        await fetch(`${API_BASE}/api/motors/stop`, { method: "POST" });
        fetchStatus();
    } catch (err) {
        console.error("Stop request failed:", err);
    }
}

// Start polling status every 1000ms
fetchStatus();
setInterval(fetchStatus, 1000);
