const API_BASE = "";

let currentStepSize = 1.0;
let driversEnabled = true;

// Telemetry Polling
async function fetchStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/motors/status`);
        if (!res.ok) throw new Error("API Offline");
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
        statusText.textContent = data.mock_mode ? "CONNECTED (MOCK)" : "ONLINE";
    } catch (err) {
        const badge = document.getElementById("statusBadge");
        const statusText = document.getElementById("statusText");
        badge.classList.remove("connected");
        statusText.textContent = "DISCONNECTED";
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
    try {
        await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan: panDelta, tilt: tiltDelta, relative: true })
        });
        fetchStatus();
    } catch (err) {
        console.error("Move relative failed:", err);
    }
}

async function moveAbsolute(pan, tilt) {
    try {
        await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan: pan, tilt: tilt, relative: false })
        });
        fetchStatus();
    } catch (err) {
        console.error("Move absolute failed:", err);
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

// Start polling status every 500ms
fetchStatus();
setInterval(fetchStatus, 500);
