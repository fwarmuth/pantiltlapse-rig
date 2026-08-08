const API_BASE = "";

let currentStepSize = 1.0;
let driversEnabled = true;
let isMoving = false;

let latestPan = 0.0;
let latestTilt = 0.0;
let zeroConfirmed = false;

let activePlan = null;
let currentKeyframes = [];
let currentLiveGain = 1.0;

let sseEventSource = null;
let httpPollingInterval = null;

// --- Telemetry & SSE Sync ---
function updateTelemetryData(data) {
    if (data.reference) {
        zeroConfirmed = data.reference.confirmed === true;
        const badge = document.getElementById("zeroRefBadge");
        const text = document.getElementById("zeroRefText");
        if (badge && text) {
            if (zeroConfirmed) {
                badge.className = "status-badge confirmed";
                text.textContent = "ZERO CONFIRMED";
            } else {
                badge.className = "status-badge unconfirmed";
                text.textContent = "ZERO UNCONFIRMED";
            }
        }
    }

    if (data.motors) {
        const m = data.motors;
        latestPan = m.pan;
        latestTilt = m.tilt;

        document.getElementById("valPan").textContent = `${m.pan.toFixed(2)}°`;
        document.getElementById("valTilt").textContent = `${m.tilt.toFixed(2)}°`;

        driversEnabled = m.drivers_enabled !== false;
        const driverBtn = document.getElementById("btnDriverToggle");
        if (driverBtn) {
            driverBtn.textContent = driversEnabled ? "Disable Drivers" : "Enable Drivers";
        }

        const badge = document.getElementById("statusBadge");
        const statusText = document.getElementById("statusText");
        if (badge && statusText) {
            if (m.connected) {
                badge.className = "status-badge connected";
                statusText.textContent = m.mock_mode ? "MOTORS (MOCK)" : "MOTORS OK";
            } else {
                badge.className = "status-badge unconfirmed";
                statusText.textContent = "MOTORS DISCONNECTED";
            }
        }
    }

    if (data.camera) {
        const c = data.camera;
        const badge = document.getElementById("cameraStatusBadge");
        const statusText = document.getElementById("cameraStatusText");
        if (badge && statusText) {
            badge.classList.add("connected");
            statusText.textContent = c.mock_mode ? "CAMERA (MOCK)" : "CAMERA OK";
        }
    }
}

function initSSE() {
    if (window.EventSource) {
        try {
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
            sseEventSource.onerror = () => {
                if (sseEventSource) {
                    sseEventSource.close();
                    sseEventSource = null;
                }
                startHTTPPollingFallback();
            };
        } catch (e) {
            startHTTPPollingFallback();
        }
    } else {
        startHTTPPollingFallback();
    }
}

function startHTTPPollingFallback() {
    if (!httpPollingInterval) {
        fetchStatus();
        httpPollingInterval = setInterval(fetchStatus, 1000);
    }
}

async function fetchStatus() {
    if (isMoving) return;
    try {
        const rigRes = await fetch(`${API_BASE}/api/rig/status`);
        const motorRes = await fetch(`${API_BASE}/api/motors/status`);
        const cameraRes = await fetch(`${API_BASE}/api/camera/status`);

        const rigData = rigRes.ok ? await rigRes.json() : null;
        const motors = motorRes.ok ? await motorRes.json() : null;
        const camera = cameraRes.ok ? await cameraRes.json() : null;

        updateTelemetryData({
            reference: rigData ? rigData.reference : null,
            motors,
            camera
        });
    } catch (err) {
        console.error("HTTP Polling error:", err);
    }
}

// --- Rig Safety & Zero Reference ---
async function confirmZeroReference() {
    try {
        const res = await fetch(`${API_BASE}/api/rig/confirm-zero`, { method: "POST" });
        const data = await res.json();
        if (data.status === "OK") {
            zeroConfirmed = true;
            updateTelemetryData({ reference: data.reference });
            alert("Physical zero reference confirmed!");
        }
    } catch (err) {
        console.error("Confirm zero failed:", err);
    }
}

async function reconnectMotors() {
    try {
        const res = await fetch(`${API_BASE}/api/motors/reconnect`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            updateTelemetryData({ motors: data.motors });
            alert("Serial port reconnected successfully!");
        } else {
            alert(`Reconnect failed: ${data.detail ? data.detail.message : "Port busy or unavailable"}`);
        }
    } catch (err) {
        console.error("Reconnect motors failed:", err);
    }
}

async function toggleDrivers() {
    try {
        const res = await fetch(`${API_BASE}/api/motors/drivers`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enable: !driversEnabled })
        });
        const data = await res.json();
        if (data.reference) {
            updateTelemetryData({ reference: data.reference });
        }
    } catch (err) {
        console.error("Toggle drivers failed:", err);
    }
}

async function stopMotors() {
    try {
        await fetch(`${API_BASE}/api/motors/stop`, { method: "POST" });
    } catch (err) {
        console.error("Emergency stop failed:", err);
    }
}

// --- Manual Motor Jogging ---
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

function getStepSize() { return currentStepSize; }

async function moveRelative(panDelta, tiltDelta) {
    isMoving = true;
    try {
        const res = await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan: panDelta, tilt: tiltDelta, relative: true })
        });
        const data = await res.json();
        if (!res.ok) {
            alert(`Move error: ${data.detail ? data.detail.message : "Failed"}`);
        }
    } catch (err) {
        console.error("Move relative error:", err);
    } finally {
        isMoving = false;
    }
}

async function moveAbsolute(pan, tilt) {
    isMoving = true;
    try {
        const res = await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan: pan, tilt: tilt, relative: false })
        });
        const data = await res.json();
        if (!res.ok) {
            alert(`Move error: ${data.detail ? data.detail.message : "Failed"}`);
        }
    } catch (err) {
        console.error("Move absolute error:", err);
    } finally {
        isMoving = false;
    }
}

let availableCameraChoices = {
    iso: ["100", "200", "400", "800", "1600", "3200", "6400", "12800"],
    shutter_speed: ["1/4000", "1/2000", "1/1000", "1/500", "1/250", "1/125", "1/60", "1/30", "1/15", "1/8", "1/4", "1/2", "1", "2", "4", "8", "15", "30"],
    aperture: ["f/1.4", "f/1.8", "f/2", "f/2.8", "f/3.5", "f/4", "f/5.6", "f/8", "f/11", "f/16", "f/22"]
};

async function fetchCameraChoices() {
    try {
        const res = await fetch(`${API_BASE}/api/camera/config/choices`);
        if (res.ok) {
            const data = await res.json();
            if (data.status === "OK" && data.choices) {
                availableCameraChoices = data.choices;
                populateCameraDropdowns();
            }
        } else {
            console.warn("Camera choices endpoint returned status:", res.status);
            populateCameraDropdowns();
        }
    } catch (err) {
        console.error("Failed to fetch camera choices:", err);
        populateCameraDropdowns();
    }
}

function populateCameraDropdowns() {
    const dropdownMap = {
        prevIso: availableCameraChoices.iso || [],
        acqIso: availableCameraChoices.iso || [],
        prevShutter: availableCameraChoices.shutter_speed || [],
        acqShutter: availableCameraChoices.shutter_speed || [],
        prevAperture: availableCameraChoices.aperture || [],
        acqAperture: availableCameraChoices.aperture || []
    };

    for (const [id, options] of Object.entries(dropdownMap)) {
        const selectEl = document.getElementById(id);
        if (!selectEl) continue;

        const currentValue = selectEl.value;
        selectEl.innerHTML = "";

        options.forEach(optVal => {
            const opt = document.createElement("option");
            opt.value = optVal;
            opt.textContent = optVal;
            selectEl.appendChild(opt);
        });

        if (currentValue) {
            setSelectValueOrAppend(id, currentValue);
        }
    }
}

function setSelectValueOrAppend(selectId, value) {
    const selectEl = document.getElementById(selectId);
    if (!selectEl) return;
    const strVal = String(value);

    let found = false;
    for (let i = 0; i < selectEl.options.length; i++) {
        if (selectEl.options[i].value === strVal) {
            found = true;
            break;
        }
    }

    if (!found && strVal) {
        const customOpt = document.createElement("option");
        customOpt.value = strVal;
        customOpt.textContent = strVal;
        selectEl.appendChild(customOpt);
    }

    selectEl.value = strVal;
}

// --- Sequence Plan Management ---
async function loadPlansList() {
    try {
        const res = await fetch(`${API_BASE}/api/plans`);
        const plans = await res.json();
        const select = document.getElementById("selectPlan");
        select.innerHTML = '<option value="">-- Create or Select Plan --</option>';
        plans.forEach(p => {
            const opt = document.createElement("option");
            opt.value = p.id;
            opt.textContent = `${p.name} (${p.total_shots} shots, ${p.duration_s}s)`;
            select.appendChild(opt);
        });

        if (activePlan && activePlan.id) {
            select.value = activePlan.id;
        }
    } catch (err) {
        console.error("Failed to load plans:", err);
    }
}

async function onPlanSelected(planId) {
    if (!planId) return;
    try {
        const res = await fetch(`${API_BASE}/api/plans/${planId}`);
        activePlan = await res.json();
        activePlan.isSaved = true;

        document.getElementById("planName").value = activePlan.name || "";
        document.getElementById("planDesc").value = activePlan.description || "";
        document.getElementById("planTotalShots").value = activePlan.schedule.total_shots || 10;
        document.getElementById("planInterval").value = activePlan.schedule.interval_s || 5.0;
        document.getElementById("planSettle").value = activePlan.schedule.settle_time_s || 0.5;

        setSelectValueOrAppend("acqIso", activePlan.acquisition.iso || "400");
        setSelectValueOrAppend("acqShutter", activePlan.acquisition.shutter_speed || "1/125");
        setSelectValueOrAppend("acqAperture", activePlan.acquisition.aperture || "f/8");

        setSelectValueOrAppend("prevIso", activePlan.preview.iso || "3200");
        setSelectValueOrAppend("prevShutter", activePlan.preview.shutter_speed || "1/4");
        setSelectValueOrAppend("prevAperture", activePlan.preview.aperture || "f/2.8");

        currentKeyframes = activePlan.trajectory.keyframes || [];
        normalizeKeyframesProgress();
        renderKeyframesTable();
        updateTrajectoryPreview();
        loadTestShotGallery();
        fetchDryRunStatus();
    } catch (err) {
        console.error("Failed to load plan detail:", err);
    }
}

function createNewPlan() {
    activePlan = {
        id: crypto.randomUUID(),
        revision: 1,
        isSaved: false,
        name: "New Time-lapse Plan",
        description: "Custom keyframe sequence",
        schedule: { total_shots: 20, interval_s: 5.0, settle_time_s: 0.5 },
        acquisition: { iso: "400", shutter_speed: "1/125", aperture: "f/8" },
        preview: { iso: "3200", shutter_speed: "1/4", aperture: "f/2.8" },
        trajectory: {
            keyframes: [
                { progress: 0.0, pose: { pan_deg: 0.0, tilt_deg: 0.0 }, outgoing_mode: "linear", tangent_scale: 1.0 },
                { progress: 1.0, pose: { pan_deg: 90.0, tilt_deg: 45.0 }, outgoing_mode: "smooth", tangent_scale: 1.0 }
            ]
        }
    };

    document.getElementById("selectPlan").value = "";
    document.getElementById("planName").value = activePlan.name;
    document.getElementById("planDesc").value = activePlan.description;
    currentKeyframes = activePlan.trajectory.keyframes;

    setSelectValueOrAppend("acqIso", "400");
    setSelectValueOrAppend("acqShutter", "1/125");
    setSelectValueOrAppend("acqAperture", "f/8");

    setSelectValueOrAppend("prevIso", "3200");
    setSelectValueOrAppend("prevShutter", "1/4");
    setSelectValueOrAppend("prevAperture", "f/2.8");

    normalizeKeyframesProgress();
    renderKeyframesTable();
    updateTrajectoryPreview();
}

async function saveCurrentPlan() {
    if (!activePlan) {
        createNewPlan();
    }

    activePlan.name = document.getElementById("planName").value || "Untitled Plan";
    activePlan.description = document.getElementById("planDesc").value || "";
    activePlan.schedule.total_shots = parseInt(document.getElementById("planTotalShots").value) || 10;
    activePlan.schedule.interval_s = parseFloat(document.getElementById("planInterval").value) || 5.0;
    activePlan.schedule.settle_time_s = parseFloat(document.getElementById("planSettle").value) || 0.5;

    activePlan.acquisition.iso = document.getElementById("acqIso").value || "400";
    activePlan.acquisition.shutter_speed = document.getElementById("acqShutter").value || "1/125";
    activePlan.acquisition.aperture = document.getElementById("acqAperture").value || "f/8";

    activePlan.preview.iso = document.getElementById("prevIso").value || "3200";
    activePlan.preview.shutter_speed = document.getElementById("prevShutter").value || "1/4";
    activePlan.preview.aperture = document.getElementById("prevAperture").value || "f/2.8";

    normalizeKeyframesProgress();
    activePlan.trajectory.keyframes = currentKeyframes;

    try {
        const isUpdate = activePlan.isSaved === true;
        const url = isUpdate ? `${API_BASE}/api/plans/${activePlan.id}` : `${API_BASE}/api/plans`;
        const method = isUpdate ? "PUT" : "POST";

        const res = await fetch(url, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(activePlan)
        });

        const data = await res.json();
        if (res.ok) {
            activePlan = data;
            activePlan.isSaved = true;
            alert(`Plan saved successfully (Rev ${activePlan.revision})!`);
            await loadPlansList();
            document.getElementById("selectPlan").value = activePlan.id;
            updateTrajectoryPreview();
        } else {
            console.error("Save plan error payload:", data);
            const errMsg = data.detail ? (data.detail.message || JSON.stringify(data.detail)) : "Failed";
            alert(`Save error: ${errMsg}`);
        }
    } catch (err) {
        console.error("Save plan failed:", err);
    }
}

async function deleteCurrentPlan() {
    if (!activePlan || !activePlan.id) return;
    if (!confirm(`Delete plan '${activePlan.name}'?`)) return;

    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}`, { method: "DELETE" });
        if (res.ok) {
            activePlan = null;
            currentKeyframes = [];
            renderKeyframesTable();
            await loadPlansList();
            alert("Plan deleted.");
        }
    } catch (err) {
        console.error("Delete plan failed:", err);
    }
}

// --- Keyframes & Trajectory Plotting ---
function normalizeKeyframesProgress() {
    if (!currentKeyframes || currentKeyframes.length === 0) return;
    if (currentKeyframes.length === 1) {
        currentKeyframes[0].progress = 0.0;
        return;
    }

    const count = currentKeyframes.length;
    currentKeyframes[0].progress = 0.0;
    currentKeyframes[count - 1].progress = 1.0;

    for (let i = 1; i < count - 1; i++) {
        currentKeyframes[i].progress = parseFloat((i / (count - 1)).toFixed(3));
    }
}

function renderKeyframesTable() {
    const tbody = document.getElementById("keyframeTableBody");
    tbody.innerHTML = "";

    currentKeyframes.forEach((kf, idx) => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td><input type="number" class="input-field" style="width:60px;" value="${kf.progress}" min="0" max="1" step="0.05" readonly></td>
            <td><input type="number" class="input-field" style="width:70px;" value="${kf.pose.pan_deg}" step="0.5" onchange="updateKeyframe(${idx}, 'pan_deg', this.value)"></td>
            <td><input type="number" class="input-field" style="width:70px;" value="${kf.pose.tilt_deg}" min="0" max="80" step="0.5" onchange="updateKeyframe(${idx}, 'tilt_deg', this.value)"></td>
            <td>
                <select class="dropdown" style="width:80px;" onchange="updateKeyframe(${idx}, 'outgoing_mode', this.value)">
                    <option value="linear" ${kf.outgoing_mode === "linear" ? "selected" : ""}>Linear</option>
                    <option value="smooth" ${kf.outgoing_mode === "smooth" ? "selected" : ""}>Smooth</option>
                </select>
            </td>
            <td><input type="range" min="0.0" max="1.0" step="0.1" value="${kf.tangent_scale || 1.0}" style="width:60px;" onchange="updateKeyframe(${idx}, 'tangent_scale', this.value)"></td>
            <td>
                <button class="btn btn-secondary btn-small" onclick="visitKeyframePose(${idx})">🎯 Visit</button>
                <button class="btn btn-danger btn-small" onclick="removeKeyframe(${idx})">✕</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function updateKeyframe(idx, field, val) {
    if (field === "pan_deg") currentKeyframes[idx].pose.pan_deg = parseFloat(val);
    else if (field === "tilt_deg") currentKeyframes[idx].pose.tilt_deg = parseFloat(val);
    else if (field === "outgoing_mode") currentKeyframes[idx].outgoing_mode = val;
    else if (field === "tangent_scale") currentKeyframes[idx].tangent_scale = parseFloat(val);

    renderKeyframesTable();
    updateTrajectoryPreview();
}

function addCurrentPoseKeyframe() {
    currentKeyframes.push({
        progress: 1.0,
        pose: { pan_deg: latestPan, tilt_deg: latestTilt },
        outgoing_mode: "smooth",
        tangent_scale: 1.0
    });
    normalizeKeyframesProgress();
    renderKeyframesTable();
    updateTrajectoryPreview();
}

function removeKeyframe(idx) {
    if (currentKeyframes.length <= 2) {
        alert("A plan trajectory must contain at least 2 keyframes.");
        return;
    }
    currentKeyframes.splice(idx, 1);
    normalizeKeyframesProgress();
    renderKeyframesTable();
    updateTrajectoryPreview();
}

async function visitKeyframePose(idx) {
    const kf = currentKeyframes[idx];
    if (kf && kf.pose) {
        await moveAbsolute(kf.pose.pan_deg, kf.pose.tilt_deg);
    }
}

async function updateTrajectoryPreview() {
    if (!activePlan || !activePlan.id) return;
    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/trajectory`);
        if (!res.ok) return;

        const data = await res.json();
        const samples = data.samples || [];

        document.getElementById("plotDiagnostics").textContent =
            `Duration: ${data.diagnostics ? data.diagnostics.expected_duration_s : 0}s | Valid: ${data.valid}`;

        if (samples.length < 2) return;

        let panPathD = "";
        let tiltPathD = "";

        const width = 500;
        const height = 200;

        samples.forEach((s, idx) => {
            const x = s.progress * width;
            // Map pan -180..180 to SVG Y height..0
            const yPan = height - ((s.pose.pan_deg + 180) / 360 * height);
            // Map tilt 0..80 to SVG Y height..0
            const yTilt = height - ((s.pose.tilt_deg) / 80 * height);

            if (idx === 0) {
                panPathD += `M ${x.toFixed(1)} ${yPan.toFixed(1)}`;
                tiltPathD += `M ${x.toFixed(1)} ${yTilt.toFixed(1)}`;
            } else {
                panPathD += ` L ${x.toFixed(1)} ${yPan.toFixed(1)}`;
                tiltPathD += ` L ${x.toFixed(1)} ${yTilt.toFixed(1)}`;
            }
        });

        document.getElementById("pathPan").setAttribute("d", panPathD);
        document.getElementById("pathTilt").setAttribute("d", tiltPathD);
    } catch (err) {
        console.error("Update trajectory plot failed:", err);
    }
}

// --- Enhanced Live View Stream ---
async function startLiveView() {
    try {
        const res = await fetch(`${API_BASE}/api/camera/preview/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gain: currentLiveGain })
        });
        const data = await res.json();
        if (res.ok) {
            const img = document.getElementById("liveStreamImg");
            const placeholder = document.getElementById("streamPlaceholder");
            img.src = `${API_BASE}/api/camera/preview/stream?t=${new Date().getTime()}`;
            img.classList.remove("hidden");
            placeholder.classList.add("hidden");
            document.getElementById("streamState").textContent = "STREAMING";
        } else {
            alert(`Live view start error: ${data.detail ? data.detail.message : "Failed"}`);
        }
    } catch (err) {
        console.error("Start live view failed:", err);
    }
}

async function stopLiveView() {
    try {
        await fetch(`${API_BASE}/api/camera/preview/stop`, { method: "POST" });
        const img = document.getElementById("liveStreamImg");
        const placeholder = document.getElementById("streamPlaceholder");
        img.src = "";
        img.classList.add("hidden");
        placeholder.classList.remove("hidden");
        document.getElementById("streamState").textContent = "IDLE";
    } catch (err) {
        console.error("Stop live view failed:", err);
    }
}

async function applyCameraConfig(param, value) {
    try {
        const res = await fetch(`${API_BASE}/api/camera/config`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ param: param, value: String(value) })
        });
        const data = await res.json();
        if (!res.ok) {
            console.warn(`Apply camera config failed for ${param}=${value}:`, data.detail ? data.detail.message : data);
        } else {
            console.log(`Applied camera config: ${param} -> ${value}`, data);
        }
    } catch (err) {
        console.error(`Error applying camera config for ${param}=${value}:`, err);
    }
}

async function onPreviewSettingChanged(param, value) {
    if (activePlan) {
        if (!activePlan.preview) activePlan.preview = {};
        if (param === "iso") activePlan.preview.iso = value;
        if (param === "shutter_speed") activePlan.preview.shutter_speed = value;
        if (param === "aperture") activePlan.preview.aperture = value;
    }
    await applyCameraConfig(param, value);
}

async function onAcquisitionSettingChanged(param, value) {
    if (activePlan) {
        if (!activePlan.acquisition) activePlan.acquisition = {};
        if (param === "iso") activePlan.acquisition.iso = value;
        if (param === "shutter_speed") activePlan.acquisition.shutter_speed = value;
        if (param === "aperture") activePlan.acquisition.aperture = value;
    }
    await applyCameraConfig(param, value);
}

async function copyAcquisitionToPreview() {
    const isoVal = document.getElementById("acqIso").value || "400";
    const shutterVal = document.getElementById("acqShutter").value || "1/125";
    const apertureVal = document.getElementById("acqAperture").value || "f/8";

    setSelectValueOrAppend("prevIso", isoVal);
    setSelectValueOrAppend("prevShutter", shutterVal);
    setSelectValueOrAppend("prevAperture", apertureVal);

    if (activePlan) {
        activePlan.preview = { iso: isoVal, shutter_speed: shutterVal, aperture: apertureVal };
    }

    await applyCameraConfig("iso", isoVal);
    await applyCameraConfig("shutter_speed", shutterVal);
    await applyCameraConfig("aperture", apertureVal);
}

function updateLiveGain(gainVal) {
    currentLiveGain = parseFloat(gainVal);
    document.getElementById("valGain").textContent = `${currentLiveGain.toFixed(1)}x`;
    const img = document.getElementById("liveStreamImg");
    if (img) {
        img.style.filter = `contrast(${currentLiveGain}) brightness(${currentLiveGain})`;
    }
}

function drawLiveHistogram(imgElement) {
    const canvas = document.getElementById("canvasHistogram");
    if (!canvas || !imgElement || imgElement.naturalWidth === 0) return;

    const ctx = canvas.getContext("2d");
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const sampleCanvas = document.createElement("canvas");
    sampleCanvas.width = 160;
    sampleCanvas.height = 120;
    const sampleCtx = sampleCanvas.getContext("2d");

    try {
        sampleCtx.drawImage(imgElement, 0, 0, 160, 120);
        const imgData = sampleCtx.getImageData(0, 0, 160, 120).data;

        const rBins = new Array(256).fill(0);
        const gBins = new Array(256).fill(0);
        const bBins = new Array(256).fill(0);
        let maxCount = 1;

        for (let i = 0; i < imgData.length; i += 4) {
            const r = imgData[i];
            const g = imgData[i + 1];
            const b = imgData[i + 2];
            rBins[r]++;
            gBins[g]++;
            bBins[b]++;
            if (rBins[r] > maxCount) maxCount = rBins[r];
            if (gBins[g] > maxCount) maxCount = gBins[g];
            if (bBins[b] > maxCount) maxCount = bBins[b];
        }

        const binWidth = width / 256;
        ctx.lineWidth = 1.5;

        // Red Channel
        ctx.strokeStyle = "rgba(239, 68, 68, 0.85)";
        ctx.beginPath();
        for (let i = 0; i < 256; i++) {
            const h = (rBins[i] / maxCount) * (height - 6);
            if (i === 0) ctx.moveTo(0, height - h);
            else ctx.lineTo(i * binWidth, height - h);
        }
        ctx.stroke();

        // Green Channel
        ctx.strokeStyle = "rgba(34, 197, 94, 0.85)";
        ctx.beginPath();
        for (let i = 0; i < 256; i++) {
            const h = (gBins[i] / maxCount) * (height - 6);
            if (i === 0) ctx.moveTo(0, height - h);
            else ctx.lineTo(i * binWidth, height - h);
        }
        ctx.stroke();

        // Blue Channel
        ctx.strokeStyle = "rgba(56, 189, 248, 0.85)";
        ctx.beginPath();
        for (let i = 0; i < 256; i++) {
            const h = (bBins[i] / maxCount) * (height - 6);
            if (i === 0) ctx.moveTo(0, height - h);
            else ctx.lineTo(i * binWidth, height - h);
        }
        ctx.stroke();

    } catch (e) {
        // Fallback for CORS or missing image buffer
    }
}

// --- Test Shots Gallery ---
async function triggerPlanTestShot() {
    if (!activePlan || !activePlan.id) return;

    const isoVal = document.getElementById("acqIso") ? document.getElementById("acqIso").value : "400";
    const shutterVal = document.getElementById("acqShutter") ? document.getElementById("acqShutter").value : "1/125";
    const apertureVal = document.getElementById("acqAperture") ? document.getElementById("acqAperture").value : "f/8";

    if (!activePlan.acquisition) activePlan.acquisition = {};
    activePlan.acquisition.iso = isoVal;
    activePlan.acquisition.shutter_speed = shutterVal;
    activePlan.acquisition.aperture = apertureVal;

    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/test-shots`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                iso: isoVal,
                shutter_speed: shutterVal,
                aperture: apertureVal
            })
        });
        const data = await res.json();
        if (res.ok) {
            alert("Test shot captured successfully!");
            loadTestShotGallery();
        } else {
            alert(`Test shot error: ${data.detail ? data.detail.message : "Failed"}`);
        }
    } catch (err) {
        console.error("Trigger test shot failed:", err);
    }
}

async function loadTestShotGallery() {
    if (!activePlan || !activePlan.id) return;
    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/test-shots`);
        const shots = await res.json();
        const gallery = document.getElementById("testShotGallery");
        gallery.innerHTML = "";

        if (shots.length === 0) {
            gallery.innerHTML = '<span class="placeholder-text">No test shots captured for this plan yet</span>';
            return;
        }

        shots.forEach(s => {
            const item = document.createElement("div");
            item.className = "gallery-item";
            item.onclick = () => openMetaModal(s);
            item.innerHTML = `
                <img src="${API_BASE}/api/plans/${activePlan.id}/test-shots/${s.shot_id}/artifacts/preview" alt="Preview">
                <div class="gallery-caption">${s.shot_id.substring(0, 8)}...</div>
            `;
            gallery.appendChild(item);
        });
    } catch (err) {
        console.error("Load test shots failed:", err);
    }
}

function openMetaModal(shotMeta) {
    document.getElementById("metaJsonDisplay").textContent = JSON.stringify(shotMeta, null, 2);
    document.getElementById("metaModal").classList.remove("hidden");
}

function closeMetaModal() {
    document.getElementById("metaModal").classList.add("hidden");
}

// --- Motion Dry Run Rehearsal ---
async function startDryRun() {
    if (!activePlan || !activePlan.id) {
        alert("Please select a plan first.");
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/dry-run/start`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            pollDryRunProgress();
        } else {
            alert(`Dry run error: ${data.detail ? data.detail.message : "Failed"}`);
        }
    } catch (err) {
        console.error("Start dry run failed:", err);
    }
}

async function cancelDryRun() {
    if (!activePlan || !activePlan.id) return;
    try {
        await fetch(`${API_BASE}/api/plans/${activePlan.id}/dry-run/cancel`, { method: "POST" });
    } catch (err) {
        console.error("Cancel dry run failed:", err);
    }
}

async function fetchDryRunStatus() {
    if (!activePlan || !activePlan.id) return;
    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/dry-run/status`);
        if (!res.ok) return;

        const data = await res.json();
        const st = data.status || {};
        const rep = data.report;

        document.getElementById("dryRunValShot").textContent = `${st.current_shot || 0} / ${st.total_shots || 0}`;
        document.getElementById("dryRunValPct").textContent = `${st.progress_pct || 0}%`;
        document.getElementById("dryRunProgressBar").style.width = `${st.progress_pct || 0}%`;

        const badge = document.getElementById("badgeReportStatus");
        if (rep) {
            if (rep.stale) {
                badge.className = "badge stale";
                badge.textContent = "Clearance: REHEARSAL STALE";
            } else {
                badge.className = "badge valid";
                badge.textContent = "Clearance: REHEARSAL VALID";
            }
        } else {
            badge.className = "badge";
            badge.textContent = "Clearance: UNTESTED";
        }
    } catch (err) {
        console.error("Fetch dry run status failed:", err);
    }
}

function pollDryRunProgress() {
    const interval = setInterval(async () => {
        await fetchDryRunStatus();
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/dry-run/status`);
        if (res.ok) {
            const data = await res.json();
            const state = data.status.state;
            if (state !== "RUNNING") {
                clearInterval(interval);
            }
        }
    }, 800);
}

// Initial Boot Sequence
initSSE();
fetchCameraChoices();
loadPlansList();
createNewPlan();
