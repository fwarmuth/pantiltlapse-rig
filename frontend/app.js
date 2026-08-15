/**
 * CameraCommander - 5-Step Trajectory & Timelapse Studio Application Logic
 */

const API_BASE = "";

// --- Application State ---
let currentStep = 1;
let currentStepSize = 1.0;
let driversEnabled = true;
let isMoving = false;

let latestPan = 0.0;
let latestTilt = 0.0;
let zeroConfirmed = false;
let motorsConnected = false;
let cameraConnected = false;
let activeCoordinatorMode = "IDLE";

// Plan State
let activePlan = null;
let currentKeyframes = [
    { progress: 0.0, pose: { pan_deg: 0.0, tilt_deg: 0.0 }, outgoing_mode: "smooth", tangent_scale: 1.0 },
    { progress: 1.0, pose: { pan_deg: 45.0, tilt_deg: 15.0 }, outgoing_mode: "smooth", tangent_scale: 1.0 }
];

// Live View & Post-Processing State
let isLiveViewActive = false;
let liveViewFps = 0.0;
let lastFrameTime = performance.now();
let streamPollingTimer = null;
let enhancementEnabled = true;
let enhanceMode = "clahe";
let filterGain = 1.5;
let filterContrast = 1.3;
let filterClipLimit = 3.0;

// Execution & Dry Run State
let dryRunActive = false;
let executionActive = false;
let executionPaused = false;
let executionStartTime = null;
let executionIntervalTimer = null;
let capturedPhotos = [];

// SSE / Polling
let sseEventSource = null;
let httpPollingInterval = null;

// ==========================================================================
// 1. Wizard Step Navigation
// ==========================================================================

function goToStep(stepNum) {
    if (stepNum < 1 || stepNum > 5) return;
    currentStep = stepNum;

    // Update Stepper Nav Buttons
    for (let i = 1; i <= 5; i++) {
        const btn = document.getElementById(`stepBtn${i}`);
        const panel = document.getElementById(`stepPanel${i}`);
        if (btn && panel) {
            btn.classList.toggle("active", i === stepNum);
            panel.classList.toggle("active", i === stepNum);
            if (i < stepNum) {
                btn.classList.add("completed");
            } else {
                btn.classList.remove("completed");
            }
        }
    }

    // Step-Specific Initializations
    if (stepNum === 1) {
        // Step 1: Framing
        updateKeyframeRigBadges();
    } else if (stepNum === 2) {
        // Step 2: Sequence Plan
        syncPlanInputs();
    } else if (stepNum === 3) {
        // Step 3: Key Poses
        renderKeyframeTable();
        updateTrajectoryPreview();
        updateKeyframeRigBadges();
    } else if (stepNum === 4) {
        // Step 4: Acquisition
        updateTimingCalculations();
        loadTestShotsList();
    } else if (stepNum === 5) {
        // Step 5: Review & Execution
        updatePreFlightChecklist();
        updateExecutionSummary();
    }
}

// ==========================================================================
// 2. Real-Time Telemetry & SSE Sync
// ==========================================================================

function updateTelemetryData(data) {
    // Reference / Zero Status
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

    // Motors Status
    if (data.motors) {
        const m = data.motors;
        latestPan = m.pan ?? 0.0;
        latestTilt = m.tilt ?? 0.0;
        motorsConnected = m.connected === true;

        const panEl = document.getElementById("valPan");
        const tiltEl = document.getElementById("valTilt");
        if (panEl) panEl.textContent = `${latestPan.toFixed(2)}°`;
        if (tiltEl) tiltEl.textContent = `${latestTilt.toFixed(2)}°`;

        updateKeyframeRigBadges();

        driversEnabled = m.drivers_enabled !== false;
        const driverBtn = document.getElementById("btnDriverToggle");
        const jogBadge = document.getElementById("jogStatusBadge");
        if (driverBtn) {
            driverBtn.textContent = driversEnabled ? "Disable Drivers" : "Enable Drivers";
        }
        if (jogBadge) {
            jogBadge.textContent = driversEnabled ? "Drivers Active" : "Drivers Disabled";
            jogBadge.className = driversEnabled ? "badge success" : "badge danger";
        }

        const badge = document.getElementById("statusBadge");
        const statusText = document.getElementById("statusText");
        if (badge && statusText) {
            if (m.connected) {
                badge.className = "status-badge connected";
                statusText.textContent = "MOTORS OK";
            } else {
                badge.className = "status-badge unconfirmed";
                statusText.textContent = "MOTORS OFF";
            }
        }
    }

    // Camera Status
    if (data.camera) {
        const c = data.camera;
        cameraConnected = c.connected === true;
        const badge = document.getElementById("cameraStatusBadge");
        const statusText = document.getElementById("cameraStatusText");
        if (badge && statusText) {
            if (cameraConnected) {
                badge.className = "status-badge connected";
                statusText.textContent = c.mock_mode ? "CAMERA (SIM)" : "CAMERA OK";
            } else {
                badge.className = "status-badge unconfirmed";
                statusText.textContent = "CAMERA OFF";
            }
        }
    }

    // Coordinator Lock Mode
    if (data.coordinator) {
        activeCoordinatorMode = data.coordinator.active_mode || "IDLE";
        const modeBadge = document.getElementById("modeBadge");
        const modeText = document.getElementById("modeText");
        if (modeBadge && modeText) {
            modeText.textContent = activeCoordinatorMode;
            modeBadge.className = activeCoordinatorMode === "IDLE" ? "status-badge mode-badge" : "status-badge mode-badge active-lock";
        }
    }

    // Dry Run Telemetry
    if (data.dry_run) {
        updateDryRunTelemetry(data.dry_run);
    }

    // Timelapse Execution Telemetry
    if (data.timelapse) {
        updateTimelapseTelemetry(data.timelapse);
    }

    // Update Checklist on Step 5
    if (currentStep === 5) {
        updatePreFlightChecklist();
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

function updateKeyframeRigBadges() {
    const p = document.getElementById("keyframeCurrPan");
    const t = document.getElementById("keyframeCurrTilt");
    if (p) p.textContent = `${latestPan.toFixed(2)}°`;
    if (t) t.textContent = `${latestTilt.toFixed(2)}°`;
}

// ==========================================================================
// 3. Step 1: Raw Motor Movement & Zero Reference
// ==========================================================================

function getStepSize() {
    return currentStepSize;
}

function setStepSize(deg) {
    currentStepSize = deg;
    const buttons = document.querySelectorAll("#jogStepSegments .segment");
    buttons.forEach((btn) => {
        const step = parseFloat(btn.getAttribute("data-step"));
        btn.classList.toggle("active", Math.abs(step - deg) < 1e-4);
    });
}

async function moveRelative(dPan, dTilt) {
    if (isMoving) return;
    isMoving = true;
    try {
        const res = await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan: dPan, tilt: dTilt, relative: true })
        });
        const data = await res.json();
        if (res.ok) {
            latestPan += dPan;
            latestTilt += dTilt;
            const panEl = document.getElementById("valPan");
            const tiltEl = document.getElementById("valTilt");
            if (panEl) panEl.textContent = `${latestPan.toFixed(2)}°`;
            if (tiltEl) tiltEl.textContent = `${latestTilt.toFixed(2)}°`;
            updateKeyframeRigBadges();
        } else {
            alert(data.detail?.message || "Move failed");
        }
    } catch (err) {
        console.error("Move request error:", err);
    } finally {
        isMoving = false;
    }
}

async function moveAbsolute(pan, tilt) {
    if (isMoving) return;
    isMoving = true;
    try {
        const res = await fetch(`${API_BASE}/api/motors/move`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pan, tilt, relative: false })
        });
        const data = await res.json();
        if (res.ok) {
            latestPan = pan;
            latestTilt = tilt;
            const panEl = document.getElementById("valPan");
            const tiltEl = document.getElementById("valTilt");
            if (panEl) panEl.textContent = `${latestPan.toFixed(2)}°`;
            if (tiltEl) tiltEl.textContent = `${latestTilt.toFixed(2)}°`;
            updateKeyframeRigBadges();
        } else {
            alert(data.detail?.message || "Move absolute failed");
        }
    } catch (err) {
        console.error("Move absolute error:", err);
    } finally {
        isMoving = false;
    }
}

async function confirmZeroReference() {
    try {
        const res = await fetch(`${API_BASE}/api/rig/confirm-zero`, { method: "POST" });
        const data = await res.json();
        if (data.status === "OK") {
            zeroConfirmed = true;
            latestPan = 0.0;
            latestTilt = 0.0;
            const panEl = document.getElementById("valPan");
            const tiltEl = document.getElementById("valTilt");
            if (panEl) panEl.textContent = "0.00°";
            if (tiltEl) tiltEl.textContent = "0.00°";
            updateTelemetryData({ reference: data.reference, motors: data.motors });
            updateKeyframeRigBadges();
            alert("🎯 Origin reset to current position (0.00°, 0.00°) & Zero Reference Confirmed!");
        }
    } catch (err) {
        console.error("Confirm zero failed:", err);
    }
}

async function toggleDrivers() {
    const targetState = !driversEnabled;
    if (!targetState) {
        const ok = confirm("⚠️ Disabling motor drivers allows the rig to move freely and INVALIDATES the zero reference. Continue?");
        if (!ok) return;
    }
    try {
        const res = await fetch(`${API_BASE}/api/motors/drivers`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ enable: targetState })
        });
        const data = await res.json();
        if (data.status === "OK") {
            driversEnabled = targetState;
            updateTelemetryData({
                motors: { drivers_enabled: targetState, connected: motorsConnected, pan: latestPan, tilt: latestTilt },
                reference: data.reference
            });
        }
    } catch (err) {
        console.error("Toggle drivers failed:", err);
    }
}

async function reconnectMotors() {
    try {
        const res = await fetch(`${API_BASE}/api/motors/reconnect`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            updateTelemetryData({ motors: data.motors });
            alert("Motor controller reconnected successfully.");
        } else {
            alert(data.detail?.message || "Failed to connect to motor serial port");
        }
    } catch (err) {
        console.error("Reconnect error:", err);
    }
}

async function stopMotors() {
    try {
        await fetch(`${API_BASE}/api/motors/stop`, { method: "POST" });
        isMoving = false;
        dryRunActive = false;
        executionActive = false;
    } catch (err) {
        console.error("Emergency stop failed:", err);
    }
}

// ==========================================================================
// 4. Live Framing Preview & Client-Side Image Processing (CLAHE, Gain, etc.)
// ==========================================================================

function toggleLiveView() {
    if (isLiveViewActive) {
        stopLiveView();
    } else {
        startLiveView();
    }
}

let isFetchingFrame = false;
let frameFetchAbortController = null;

async function startLiveView() {
    try {
        const res = await fetch(`${API_BASE}/api/camera/preview/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ gain: filterGain, plan_id: activePlan ? activePlan.id : null })
        });
        if (res.ok) {
            isLiveViewActive = true;
            document.getElementById("btnToggleLiveView").textContent = "⏹ Stop Stream";
            document.getElementById("streamPlaceholder").classList.add("hidden");
            document.getElementById("streamState").textContent = "STREAMING";

            frameFetchAbortController = new AbortController();
            runFrameFetchLoop();
        } else {
            const data = await res.json();
            alert(data.detail?.message || "Failed to start camera live view");
        }
    } catch (err) {
        console.error("Start live view error:", err);
    }
}

async function stopLiveView() {
    isLiveViewActive = false;
    if (frameFetchAbortController) {
        frameFetchAbortController.abort();
        frameFetchAbortController = null;
    }
    try {
        await fetch(`${API_BASE}/api/camera/preview/stop`, { method: "POST" });
    } catch (e) {}

    document.getElementById("btnToggleLiveView").textContent = "▶ Start Stream";
    document.getElementById("streamPlaceholder").classList.remove("hidden");
    document.getElementById("streamState").textContent = "IDLE";
    document.getElementById("streamFps").textContent = "0.0";
}

async function runFrameFetchLoop() {
    const canvas = document.getElementById("canvasEnhancedPreview");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });

    while (isLiveViewActive) {
        if (!isFetchingFrame) {
            isFetchingFrame = true;
            try {
                const res = await fetch(`${API_BASE}/api/camera/preview/frame?t=${Date.now()}`, {
                    signal: frameFetchAbortController ? frameFetchAbortController.signal : undefined
                });
                if (res.ok) {
                    const blob = await res.blob();
                    const bitmap = await createImageBitmap(blob);

                    if (canvas.width !== bitmap.width || canvas.height !== bitmap.height) {
                        canvas.width = bitmap.width;
                        canvas.height = bitmap.height;
                        document.getElementById("streamRes").textContent = `${canvas.width}×${canvas.height}`;
                    }

                    ctx.drawImage(bitmap, 0, 0);
                    bitmap.close();

                    if (enhancementEnabled) {
                        const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                        applyImageEnhancement(imgData, enhanceMode, filterGain, filterContrast, filterClipLimit);
                        ctx.putImageData(imgData, 0, 0);
                    }

                    drawHistogramFromCanvas(canvas);

                    // Measured FPS
                    const now = performance.now();
                    const delta = now - lastFrameTime;
                    lastFrameTime = now;
                    if (delta > 0) {
                        liveViewFps = 0.8 * liveViewFps + 0.2 * (1000 / delta);
                        document.getElementById("streamFps").textContent = liveViewFps.toFixed(1);
                    }
                }
            } catch (err) {
                if (err.name !== "AbortError") {
                    console.debug("Frame fetch error:", err);
                }
            } finally {
                isFetchingFrame = false;
            }
        }
        await new Promise((r) => setTimeout(r, 60)); // ~15 FPS pacing
    }
}

function toggleEnhancementFilter(enabled) {
    enhancementEnabled = enabled;
}

function updateEnhancementSettings() {
    const selMode = document.getElementById("selEnhanceMode");
    const sGain = document.getElementById("sliderGain");
    const sContrast = document.getElementById("sliderContrast");
    const sClip = document.getElementById("sliderClipLimit");

    if (selMode) enhanceMode = selMode.value;
    if (sGain) filterGain = parseFloat(sGain.value);
    if (sContrast) filterContrast = parseFloat(sContrast.value);
    if (sClip) filterClipLimit = parseFloat(sClip.value);

    const lblG = document.getElementById("lblValGain");
    const lblC = document.getElementById("lblValContrast");
    const lblClip = document.getElementById("lblValClip");

    if (lblG) lblG.textContent = `${filterGain.toFixed(1)}x`;
    if (lblC) lblC.textContent = `${filterContrast.toFixed(1)}x`;
    if (lblClip) lblClip.textContent = `${filterClipLimit.toFixed(1)}`;
}

/**
 * High-performance client-side image processing for low-light camera framing.
 * Includes CLAHE (Contrast Limited Adaptive Histogram Equalization), Gain/Gamma boost, Edge detect.
 */
function applyImageEnhancement(imageData, mode, gain, contrast, clipLimit) {
    const data = imageData.data;
    const len = data.length;
    const w = imageData.width;
    const h = imageData.height;

    if (mode === "clahe") {
        applyCLAHE(data, w, h, clipLimit, gain, contrast);
    } else if (mode === "gain_gamma") {
        const factor = (259 * (contrast * 128 + 255)) / (255 * (259 - contrast * 128));
        const gamma = 1.0 / gain;
        for (let i = 0; i < len; i += 4) {
            for (let c = 0; c < 3; c++) {
                let v = data[i + c] / 255.0;
                v = Math.pow(v, gamma) * gain * 255;
                v = factor * (v - 128) + 128;
                data[i + c] = Math.min(255, Math.max(0, v));
            }
        }
    } else if (mode === "night_vision") {
        for (let i = 0; i < len; i += 4) {
            const luma = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
            const boosted = Math.min(255, Math.pow(luma / 255.0, 0.6) * 255 * gain);
            data[i] = boosted * 0.2;
            data[i + 1] = boosted;
            data[i + 2] = boosted * 0.3;
        }
    } else if (mode === "edges") {
        // Simple Sobel-like filter for manual focus assist
        const copy = new Uint8ClampedArray(data);
        for (let y = 1; y < h - 1; y++) {
            for (let x = 1; x < w - 1; x++) {
                const idx = (y * w + x) * 4;
                const left = ((y * w + (x - 1)) * 4);
                const right = ((y * w + (x + 1)) * 4);
                const up = (((y - 1) * w + x) * 4);
                const down = (((y + 1) * w + x) * 4);

                const gx = (copy[right] - copy[left]);
                const gy = (copy[down] - copy[up]);
                const edge = Math.min(255, Math.sqrt(gx * gx + gy * gy) * gain * 1.5);

                data[idx] = edge;
                data[idx + 1] = edge > 80 ? 255 : edge;
                data[idx + 2] = edge;
            }
        }
    }
}

/**
 * Fast 8x8 Grid CLAHE implementation for 8-bit image buffers
 */
function applyCLAHE(data, width, height, clipLimit, gain, contrast) {
    const gridX = 8;
    const gridY = 8;
    const tileSizeX = Math.floor(width / gridX);
    const tileSizeY = Math.floor(height / gridY);
    if (tileSizeX < 2 || tileSizeY < 2) return;

    // 1. Calculate tile histograms
    const hist = [];
    const clipVal = Math.max(1, Math.floor((tileSizeX * tileSizeY / 256) * clipLimit));

    for (let ty = 0; ty < gridY; ty++) {
        hist[ty] = [];
        for (let tx = 0; tx < gridX; tx++) {
            const hArr = new Uint32Array(256);
            const startX = tx * tileSizeX;
            const startY = ty * tileSizeY;
            const endX = (tx === gridX - 1) ? width : startX + tileSizeX;
            const endY = (ty === gridY - 1) ? height : startY + tileSizeY;

            for (let y = startY; y < endY; y++) {
                let rowOffset = y * width * 4;
                for (let x = startX; x < endX; x++) {
                    const idx = rowOffset + x * 4;
                    const luma = (data[idx] * 77 + data[idx + 1] * 150 + data[idx + 2] * 29) >> 8;
                    hArr[luma]++;
                }
            }

            // Clip histogram
            let excess = 0;
            for (let i = 0; i < 256; i++) {
                if (hArr[i] > clipVal) {
                    excess += hArr[i] - clipVal;
                    hArr[i] = clipVal;
                }
            }
            const binExcess = Math.floor(excess / 256);
            for (let i = 0; i < 256; i++) hArr[i] += binExcess;

            // Build CDF mapping
            const cdf = new Uint8Array(256);
            let sum = 0;
            const totalPixels = (endX - startX) * (endY - startY);
            for (let i = 0; i < 256; i++) {
                sum += hArr[i];
                cdf[i] = Math.min(255, Math.floor((sum * 255) / totalPixels));
            }
            hist[ty][tx] = cdf;
        }
    }

    // 2. Bilinear Interpolation across tiles
    for (let y = 0; y < height; y++) {
        const tyFloat = (y - tileSizeY / 2) / tileSizeY;
        let ty1 = Math.floor(tyFloat);
        let ty2 = ty1 + 1;
        const fy = tyFloat - ty1;
        ty1 = Math.max(0, Math.min(gridY - 1, ty1));
        ty2 = Math.max(0, Math.min(gridY - 1, ty2));

        const rowOffset = y * width * 4;
        for (let x = 0; x < width; x++) {
            const txFloat = (x - tileSizeX / 2) / tileSizeX;
            let tx1 = Math.floor(txFloat);
            let tx2 = tx1 + 1;
            const fx = txFloat - tx1;
            tx1 = Math.max(0, Math.min(gridX - 1, tx1));
            tx2 = Math.max(0, Math.min(gridX - 1, tx2));

            const idx = rowOffset + x * 4;
            const luma = (data[idx] * 77 + data[idx + 1] * 150 + data[idx + 2] * 29) >> 8;

            const c00 = hist[ty1][tx1][luma];
            const c10 = hist[ty1][tx2][luma];
            const c01 = hist[ty2][tx1][luma];
            const c11 = hist[ty2][tx2][luma];

            const top = c00 * (1 - fx) + c10 * fx;
            const bottom = c01 * (1 - fx) + c11 * fx;
            const eqLuma = top * (1 - fy) + bottom * fy;

            const ratio = luma > 0 ? (eqLuma / luma) * gain : gain;
            data[idx] = Math.min(255, data[idx] * ratio * contrast);
            data[idx + 1] = Math.min(255, data[idx + 1] * ratio * contrast);
            data[idx + 2] = Math.min(255, data[idx + 2] * ratio * contrast);
        }
    }
}

function drawHistogramFromCanvas(canvas) {
    const histCanvas = document.getElementById("canvasHistogram");
    if (!histCanvas) return;
    const hCtx = histCanvas.getContext("2d");
    const ctx = canvas.getContext("2d");

    const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const d = imgData.data;
    const rH = new Uint32Array(256);
    const gH = new Uint32Array(256);
    const bH = new Uint32Array(256);

    for (let i = 0; i < d.length; i += 16) {
        rH[d[i]]++;
        gH[d[i + 1]]++;
        bH[d[i + 2]]++;
    }

    let maxCount = 1;
    for (let i = 0; i < 256; i++) {
        if (rH[i] > maxCount) maxCount = rH[i];
        if (gH[i] > maxCount) maxCount = gH[i];
        if (bH[i] > maxCount) maxCount = bH[i];
    }

    hCtx.fillStyle = "#020617";
    hCtx.fillRect(0, 0, histCanvas.width, histCanvas.height);

    const w = histCanvas.width;
    const h = histCanvas.height;

    // Draw R, G, B channels
    drawChannelCurve(hCtx, rH, maxCount, w, h, "rgba(244, 63, 94, 0.6)");
    drawChannelCurve(hCtx, gH, maxCount, w, h, "rgba(52, 211, 153, 0.6)");
    drawChannelCurve(hCtx, bH, maxCount, w, h, "rgba(56, 189, 248, 0.6)");
}

function drawChannelCurve(ctx, histArray, maxCount, w, h, color) {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.moveTo(0, h);
    for (let i = 0; i < 256; i++) {
        const x = (i / 255) * w;
        const y = h - (histArray[i] / maxCount) * (h - 2);
        ctx.lineTo(x, y);
    }
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fill();
}

// ==========================================================================
// 5. Step 2: Sequence Plan CRUD
// ==========================================================================

async function loadPlansList() {
    try {
        const res = await fetch(`${API_BASE}/api/plans`);
        if (res.ok) {
            const plans = await res.json();
            const select = document.getElementById("selectPlan");
            select.innerHTML = '<option value="">-- Create or Select Sequence Plan --</option>';
            plans.forEach((p) => {
                const opt = document.createElement("option");
                opt.value = p.id;
                opt.textContent = `${p.name} (Rev ${p.revision}, ${p.total_shots} shots)`;
                select.appendChild(opt);
            });

            if (!activePlan && plans.length > 0) {
                onPlanSelected(plans[0].id);
            }
        }
    } catch (e) {
        console.error("Load plans error:", e);
    }
}

async function onPlanSelected(planId) {
    if (!planId) {
        createNewPlan();
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/api/plans/${planId}`);
        if (res.ok) {
            activePlan = await res.json();
            currentKeyframes = JSON.parse(JSON.stringify(activePlan.trajectory.keyframes));
            syncPlanInputs();
            renderKeyframeTable();
            updateTrajectoryPreview();
        }
    } catch (e) {
        console.error("Load plan detail error:", e);
    }
}

function createNewPlan() {
    activePlan = {
        id: crypto.randomUUID(),
        revision: 1,
        name: "New Time-lapse Sequence",
        description: "",
        trajectory: {
            keyframes: [
                { progress: 0.0, pose: { pan_deg: 0.0, tilt_deg: 0.0 }, outgoing_mode: "smooth", tangent_scale: 1.0 },
                { progress: 1.0, pose: { pan_deg: 30.0, tilt_deg: 10.0 }, outgoing_mode: "smooth", tangent_scale: 1.0 }
            ]
        },
        schedule: { total_shots: 24, interval_s: 5.0, settle_time_s: 0.5 },
        acquisition: { iso: "400", shutter_speed: "1/125", aperture: "5.6", camera_format: "JPEG" },
        preview: { iso: "3200", shutter_speed: "1/4", aperture: "2.8" }
    };
    currentKeyframes = JSON.parse(JSON.stringify(activePlan.trajectory.keyframes));
    syncPlanInputs();
    renderKeyframeTable();
    updateTrajectoryPreview();
}

function syncPlanInputs() {
    if (!activePlan) return;
    document.getElementById("planName").value = activePlan.name || "";
    document.getElementById("planDesc").value = activePlan.description || "";
    document.getElementById("planTotalShots").value = activePlan.schedule?.total_shots || 20;
    document.getElementById("planInterval").value = activePlan.schedule?.interval_s || 5.0;
    document.getElementById("planSettle").value = activePlan.schedule?.settle_time_s || 0.5;

    document.getElementById("lblPlanId").textContent = activePlan.id ? activePlan.id.substring(0, 8) + "..." : "New";
    document.getElementById("lblPlanRevision").textContent = activePlan.revision || 1;
    document.getElementById("lblPlanKeyframeCount").textContent = currentKeyframes.length;
    document.getElementById("lblPlanTotalShots").textContent = activePlan.schedule?.total_shots || 20;

    // Acquisition Settings Sync
    if (activePlan.acquisition) {
        const isoEl = document.getElementById("acqIso");
        const shutterEl = document.getElementById("acqShutter");
        const apEl = document.getElementById("acqAperture");
        const fmtEl = document.getElementById("acqFormat");
        if (isoEl) isoEl.value = activePlan.acquisition.iso || "400";
        if (shutterEl) shutterEl.value = activePlan.acquisition.shutter_speed || "1/125";
        if (apEl) apEl.value = activePlan.acquisition.aperture || "5.6";
        if (fmtEl) fmtEl.value = activePlan.acquisition.camera_format || "JPEG";
    }

    updateTimingCalculations();
}

async function saveCurrentPlan() {
    if (!activePlan) createNewPlan();

    activePlan.name = document.getElementById("planName").value.trim() || "Untitled Sequence";
    activePlan.description = document.getElementById("planDesc").value.trim();
    activePlan.schedule.total_shots = parseInt(document.getElementById("planTotalShots").value, 10) || 20;
    activePlan.schedule.interval_s = parseFloat(document.getElementById("planInterval").value) || 5.0;
    activePlan.schedule.settle_time_s = parseFloat(document.getElementById("planSettle").value) || 0.5;

    activePlan.trajectory.keyframes = currentKeyframes;

    activePlan.acquisition = {
        iso: document.getElementById("acqIso").value,
        shutter_speed: document.getElementById("acqShutter").value,
        aperture: document.getElementById("acqAperture").value,
        camera_format: document.getElementById("acqFormat").value
    };

    try {
        const isExisting = document.getElementById("selectPlan").value === activePlan.id;
        const url = isExisting ? `${API_BASE}/api/plans/${activePlan.id}` : `${API_BASE}/api/plans`;
        const method = isExisting ? "PUT" : "POST";

        const res = await fetch(url, {
            method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(activePlan)
        });
        const saved = await res.json();
        if (res.ok) {
            activePlan = saved;
            alert(`💾 Plan '${saved.name}' saved successfully! (Rev ${saved.revision})`);
            await loadPlansList();
            document.getElementById("selectPlan").value = saved.id;
            syncPlanInputs();
        } else {
            alert(saved.detail?.message || "Failed to save plan");
        }
    } catch (e) {
        console.error("Save plan error:", e);
    }
}

async function deleteCurrentPlan() {
    if (!activePlan || !activePlan.id) return;
    if (!confirm(`Delete sequence plan '${activePlan.name}'?`)) return;

    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}`, { method: "DELETE" });
        if (res.ok) {
            alert("Plan deleted.");
            activePlan = null;
            await loadPlansList();
            createNewPlan();
        }
    } catch (e) {
        console.error("Delete plan error:", e);
    }
}

// ==========================================================================
// 6. Step 3: Key Poses & Interactive Trajectory Visualizer
// ==========================================================================

function renderKeyframeTable() {
    const tbody = document.getElementById("keyframeTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    // Sort by progress
    currentKeyframes.sort((a, b) => a.progress - b.progress);

    currentKeyframes.forEach((kf, idx) => {
        const tr = document.createElement("tr");

        const isStart = idx === 0;
        const isEnd = idx === currentKeyframes.length - 1;

        tr.innerHTML = `
            <td>
                <input type="number" step="0.05" min="0" max="1" value="${kf.progress.toFixed(2)}"
                    ${isStart || isEnd ? "disabled" : ""} onchange="onKeyframeProgressChange(${idx}, this.value)">
            </td>
            <td>
                <input type="number" step="0.5" value="${kf.pose.pan_deg.toFixed(1)}"
                    onchange="onKeyframePoseChange(${idx}, 'pan', this.value)">
            </td>
            <td>
                <input type="number" step="0.5" value="${kf.pose.tilt_deg.toFixed(1)}"
                    onchange="onKeyframePoseChange(${idx}, 'tilt', this.value)">
            </td>
            <td>
                <select onchange="onKeyframeModeChange(${idx}, this.value)" style="width:75px;">
                    <option value="smooth" ${kf.outgoing_mode === "smooth" ? "selected" : ""}>Smooth</option>
                    <option value="linear" ${kf.outgoing_mode === "linear" ? "selected" : ""}>Linear</option>
                </select>
            </td>
            <td>
                <button class="btn btn-secondary btn-sm" onclick="visitKeyframePose(${idx})" title="Move Rig to this pose">🎯 Go</button>
                <button class="btn btn-accent btn-sm" onclick="overwriteKeyframePoseWithCurrent(${idx})" title="Update with current rig angles">📍 Set</button>
                ${!isStart && !isEnd ? `<button class="btn btn-danger btn-sm" onclick="deleteKeyframe(${idx})">✕</button>` : ""}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

function onKeyframeProgressChange(idx, val) {
    currentKeyframes[idx].progress = Math.max(0.01, Math.min(0.99, parseFloat(val)));
    renderKeyframeTable();
    updateTrajectoryPreview();
}

function onKeyframePoseChange(idx, axis, val) {
    if (axis === "pan") currentKeyframes[idx].pose.pan_deg = parseFloat(val);
    if (axis === "tilt") currentKeyframes[idx].pose.tilt_deg = parseFloat(val);
    updateTrajectoryPreview();
}

function onKeyframeModeChange(idx, mode) {
    currentKeyframes[idx].outgoing_mode = mode;
    updateTrajectoryPreview();
}

function addCurrentPoseKeyframe() {
    // If only 2 keyframes and start is 0, update closest or append
    const pan = latestPan;
    const tilt = latestTilt;

    if (currentKeyframes.length === 2 && currentKeyframes[0].pose.pan_deg === 0 && currentKeyframes[0].pose.tilt_deg === 0) {
        currentKeyframes[0].pose.pan_deg = pan;
        currentKeyframes[0].pose.tilt_deg = tilt;
    } else {
        // Add at middle
        currentKeyframes.push({
            progress: 0.5,
            pose: { pan_deg: pan, tilt_deg: tilt },
            outgoing_mode: "smooth",
            tangent_scale: 1.0
        });
    }

    renderKeyframeTable();
    updateTrajectoryPreview();
}

function addNewIntermediateKeyframe() {
    currentKeyframes.push({
        progress: 0.5,
        pose: { pan_deg: latestPan, tilt_deg: latestTilt },
        outgoing_mode: "smooth",
        tangent_scale: 1.0
    });
    renderKeyframeTable();
    updateTrajectoryPreview();
}

function overwriteKeyframePoseWithCurrent(idx) {
    currentKeyframes[idx].pose.pan_deg = latestPan;
    currentKeyframes[idx].pose.tilt_deg = latestTilt;
    renderKeyframeTable();
    updateTrajectoryPreview();
}

function visitKeyframePose(idx) {
    const kf = currentKeyframes[idx];
    moveAbsolute(kf.pose.pan_deg, kf.pose.tilt_deg);
}

function deleteKeyframe(idx) {
    if (idx === 0 || idx === currentKeyframes.length - 1) return;
    currentKeyframes.splice(idx, 1);
    renderKeyframeTable();
    updateTrajectoryPreview();
}

// Interactive SVG Trajectory Plot
function updateTrajectoryPreview() {
    if (!activePlan) return;
    const totalShots = parseInt(document.getElementById("planTotalShots").value, 10) || 20;

    // Sort keyframes
    currentKeyframes.sort((a, b) => a.progress - b.progress);
    currentKeyframes[0].progress = 0.0;
    currentKeyframes[currentKeyframes.length - 1].progress = 1.0;

    // Sample cubic hermite trajectory locally
    const sampled = sampleTrajectoryLocal(currentKeyframes, totalShots);

    const svgW = 500;
    const svgH = 120;

    let minPan = Infinity, maxPan = -Infinity;
    let minTilt = Infinity, maxTilt = -Infinity;

    sampled.forEach(p => {
        if (p.pan < minPan) minPan = p.pan;
        if (p.pan > maxPan) maxPan = p.pan;
        if (p.tilt < minTilt) minTilt = p.tilt;
        if (p.tilt > maxTilt) maxTilt = p.tilt;
    });

    const panRange = Math.max(10, maxPan - minPan);
    const tiltRange = Math.max(10, maxTilt - minTilt);

    let panPathStr = "";
    let tiltPathStr = "";

    sampled.forEach((p, i) => {
        const x = (i / (sampled.length - 1)) * svgW;
        const yPan = svgH - ((p.pan - minPan) / panRange) * (svgH - 20) - 10;
        const yTilt = svgH - ((p.tilt - minTilt) / tiltRange) * (svgH - 20) - 10;

        panPathStr += (i === 0 ? `M ${x.toFixed(1)} ${yPan.toFixed(1)}` : ` L ${x.toFixed(1)} ${yPan.toFixed(1)}`);
        tiltPathStr += (i === 0 ? `M ${x.toFixed(1)} ${yTilt.toFixed(1)}` : ` L ${x.toFixed(1)} ${yTilt.toFixed(1)}`);
    });

    const pathPanEl = document.getElementById("pathPan");
    const pathTiltEl = document.getElementById("pathTilt");
    if (pathPanEl) pathPanEl.setAttribute("d", panPathStr);
    if (pathTiltEl) pathTiltEl.setAttribute("d", tiltPathStr);

    const diag = document.getElementById("plotDiagnostics");
    if (diag) {
        diag.textContent = `ΔPan: ${(maxPan - minPan).toFixed(1)}° | ΔTilt: ${(maxTilt - minTilt).toFixed(1)}°`;
    }

    updateTimingCalculations();
}

function sampleTrajectoryLocal(keyframes, count) {
    const points = [];
    for (let i = 0; i < count; i++) {
        const t = i / (count - 1);
        // Find segment
        let seg = 0;
        while (seg < keyframes.length - 2 && keyframes[seg + 1].progress < t) seg++;

        const k0 = keyframes[seg];
        const k1 = keyframes[seg + 1];
        const localT = (t - k0.progress) / Math.max(1e-5, (k1.progress - k0.progress));

        if (k0.outgoing_mode === "linear") {
            points.push({
                pan: k0.pose.pan_deg + (k1.pose.pan_deg - k0.pose.pan_deg) * localT,
                tilt: k0.pose.tilt_deg + (k1.pose.tilt_deg - k0.pose.tilt_deg) * localT
            });
        } else {
            // Cubic Hermite smooth
            const h00 = (1 + 2 * localT) * Math.pow(1 - localT, 2);
            const h10 = localT * Math.pow(1 - localT, 2);
            const h01 = Math.pow(localT, 2) * (3 - 2 * localT);
            const h11 = Math.pow(localT, 2) * (localT - 1);

            const dPan = (k1.pose.pan_deg - k0.pose.pan_deg);
            const dTilt = (k1.pose.tilt_deg - k0.pose.tilt_deg);

            points.push({
                pan: h00 * k0.pose.pan_deg + h10 * dPan + h01 * k1.pose.pan_deg + h11 * dPan,
                tilt: h00 * k0.pose.tilt_deg + h10 * dTilt + h01 * k1.pose.tilt_deg + h11 * dTilt
            });
        }
    }
    return points;
}

// Dry Run Rehearsal
async function startDryRun() {
    if (!activePlan) {
        alert("Please save your sequence plan first.");
        return;
    }
    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/dry-run/start`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            dryRunActive = true;
            document.getElementById("badgeReportStatus").textContent = "Clearance: REHEARSING...";
            document.getElementById("badgeReportStatus").className = "badge";
        } else {
            alert(data.detail?.message || "Dry run start failed");
        }
    } catch (e) {
        console.error("Dry run start error:", e);
    }
}

async function cancelDryRun() {
    if (!activePlan) return;
    try {
        await fetch(`${API_BASE}/api/plans/${activePlan.id}/dry-run/cancel`, { method: "POST" });
        dryRunActive = false;
    } catch (e) {}
}

function updateDryRunTelemetry(dr) {
    if (!dr) return;
    const pct = (dr.progress_pct ?? 0).toFixed(0);
    const pBar = document.getElementById("dryRunProgressBar");
    const pText = document.getElementById("dryRunValPct");
    const shotText = document.getElementById("dryRunValShot");

    if (pBar) pBar.style.width = `${pct}%`;
    if (pText) pText.textContent = `${pct}%`;
    if (shotText) shotText.textContent = `${dr.current_shot ?? 0} / ${dr.total_shots ?? 0}`;

    const badge = document.getElementById("badgeReportStatus");
    if (badge) {
        if (dr.state === "COMPLETED") {
            badge.textContent = "Clearance: VERIFIED OK";
            badge.className = "badge success";
        } else if (dr.state === "RUNNING") {
            badge.textContent = "Clearance: REHEARSING...";
            badge.className = "badge";
        } else if (dr.state === "ERROR") {
            badge.textContent = "Clearance: ERROR";
            badge.className = "badge danger";
        }
    }
}

// ==========================================================================
// 7. Step 4: Acquisition Settings & Test Shots
// ==========================================================================

function onAcquisitionSettingChanged(param, val) {
    if (!activePlan) return;
    if (!activePlan.acquisition) activePlan.acquisition = {};
    activePlan.acquisition[param] = val;
}

function updateTimingCalculations() {
    const totalShots = parseInt(document.getElementById("planTotalShots")?.value, 10) || 20;
    const interval = parseFloat(document.getElementById("planInterval")?.value) || 5.0;

    const totalSeconds = (totalShots - 1) * interval;
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = Math.floor(totalSeconds % 60);
    const videoDuration = (totalShots / 24.0).toFixed(1);

    const timingEl = document.getElementById("timingEstimateText");
    if (timingEl) {
        timingEl.textContent = `Total Runtime: ${minutes}m ${seconds}s | Video Duration at 24fps: ${videoDuration}s (${totalShots} frames)`;
    }
}

async function triggerPlanTestShot() {
    if (!activePlan) {
        alert("Please save your sequence plan first.");
        return;
    }
    const btn = document.getElementById("btnTakeTestShot");
    if (btn) btn.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/test-shots`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                iso: document.getElementById("acqIso").value,
                shutter_speed: document.getElementById("acqShutter").value,
                aperture: document.getElementById("acqAperture").value
            })
        });
        const data = await res.json();
        if (res.ok) {
            await loadTestShotsList();
        } else {
            alert(data.detail?.message || "Test shot failed");
        }
    } catch (e) {
        console.error("Test shot error:", e);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function loadTestShotsList() {
    if (!activePlan || !activePlan.id) return;
    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/test-shots`);
        if (res.ok) {
            const shots = await res.json();
            renderTestShotGallery(shots);
        }
    } catch (e) {
        console.error("Load test shots error:", e);
    }
}

function renderTestShotGallery(shots) {
    const gallery = document.getElementById("testShotGallery");
    if (!gallery) return;
    gallery.innerHTML = "";

    if (shots.length === 0) {
        gallery.innerHTML = '<div class="placeholder-box" style="grid-column:1/-1;"><span>No test shots taken yet</span></div>';
        return;
    }

    shots.forEach(s => {
        const item = document.createElement("div");
        item.className = "gallery-item";
        const thumbUrl = `${API_BASE}/api/plans/${activePlan.id}/test-shots/${s.id}/artifacts/preview.jpg`;

        item.innerHTML = `
            <img class="gallery-thumb" src="${thumbUrl}" alt="Test Shot" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'100\\' height=\\'80\\'><rect fill=\\'%23111\\' width=\\'100\\' height=\\'80\\'/><text fill=\\'%23666\\' x=\\'50%\\' y=\\'50%\\' text-anchor=\\'middle\\'>RAW</text></svg>'">
            <div class="gallery-info">
                <span class="gallery-title">${s.camera_settings?.shutter_speed || "1/125"}s f/${s.camera_settings?.aperture || "5.6"}</span>
                <span class="gallery-sub">ISO ${s.camera_settings?.iso || "400"}</span>
            </div>
        `;
        item.onclick = () => openMetaModal(s);
        gallery.appendChild(item);
    });
}

function openMetaModal(shotMeta) {
    const modal = document.getElementById("metaModal");
    const jsonPre = document.getElementById("metaJsonDisplay");
    if (modal && jsonPre) {
        jsonPre.textContent = JSON.stringify(shotMeta, null, 2);
        modal.classList.remove("hidden");
    }
}

function closeMetaModal() {
    const modal = document.getElementById("metaModal");
    if (modal) modal.classList.add("hidden");
}

// ==========================================================================
// 8. Step 5: Pre-Flight Review & Sequence Execution
// ==========================================================================

function updatePreFlightChecklist() {
    // 1. Zero confirmed
    const chkZero = document.getElementById("chkZeroRef");
    if (chkZero) {
        chkZero.className = zeroConfirmed ? "passed" : "failed";
        chkZero.innerHTML = zeroConfirmed
            ? '<span class="chk-icon">✅</span> Coordinate Zero Origin Confirmed'
            : '<span class="chk-icon">❌</span> Coordinate Zero Reference Not Confirmed';
    }

    // 2. Motors Connected
    const chkMotors = document.getElementById("chkMotors");
    if (chkMotors) {
        const ok = motorsConnected && driversEnabled;
        chkMotors.className = ok ? "passed" : "failed";
        chkMotors.innerHTML = ok
            ? '<span class="chk-icon">✅</span> Motors Connected & Drivers Active'
            : '<span class="chk-icon">❌</span> Motors Disconnected or Drivers Disabled';
    }

    // 3. Camera Connected
    const chkCam = document.getElementById("chkCamera");
    if (chkCam) {
        chkCam.className = cameraConnected ? "passed" : "failed";
        chkCam.innerHTML = cameraConnected
            ? '<span class="chk-icon">✅</span> Camera Connected & Ready'
            : '<span class="chk-icon">❌</span> Camera Disconnected';
    }

    // 4. Trajectory
    const chkTraj = document.getElementById("chkTrajectory");
    if (chkTraj) {
        const ok = currentKeyframes && currentKeyframes.length >= 2;
        chkTraj.className = ok ? "passed" : "failed";
        chkTraj.innerHTML = ok
            ? '<span class="chk-icon">✅</span> Trajectory Verified (2+ Keyframes)'
            : '<span class="chk-icon">❌</span> Trajectory Requires At Least 2 Keyframes';
    }
}

function updateExecutionSummary() {
    if (!activePlan) return;
    document.getElementById("execPlanName").textContent = activePlan.name || "Untitled";
    const total = activePlan.schedule?.total_shots || 20;
    document.getElementById("execTotalShots").textContent = total;
}

async function startSequenceExecution() {
    if (!zeroConfirmed) {
        const proceed = confirm("⚠️ Origin is unconfirmed. Do you wish to start the sequence anyway?");
        if (!proceed) return;
    }

    const total = activePlan?.schedule?.total_shots || 20;
    const interval = activePlan?.schedule?.interval_s || 5.0;
    const settle = activePlan?.schedule?.settle_time_s || 0.5;

    try {
        const res = await fetch(`${API_BASE}/api/timelapse/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                total_shots: total,
                interval_s: interval,
                pause_s: settle,
                pan_step: (currentKeyframes[currentKeyframes.length - 1].pose.pan_deg - currentKeyframes[0].pose.pan_deg) / Math.max(1, total - 1),
                tilt_step: (currentKeyframes[currentKeyframes.length - 1].pose.tilt_deg - currentKeyframes[0].pose.tilt_deg) / Math.max(1, total - 1),
                capture: true
            })
        });
        const data = await res.json();
        if (res.ok) {
            executionActive = true;
            executionPaused = false;
            executionStartTime = Date.now();
            document.getElementById("btnStartExecution").disabled = true;
            document.getElementById("btnPauseExecution").disabled = false;
            document.getElementById("btnCancelExecution").disabled = false;
            document.getElementById("liveRunStateBadge").textContent = "RUNNING";
            document.getElementById("liveRunStateBadge").className = "badge success";
        } else {
            alert(data.detail?.message || "Failed to start time-lapse sequence");
        }
    } catch (e) {
        console.error("Start execution error:", e);
    }
}

async function togglePauseExecution() {
    if (!executionActive) return;
    try {
        if (executionPaused) {
            await fetch(`${API_BASE}/api/timelapse/resume`, { method: "POST" });
            executionPaused = false;
            document.getElementById("btnPauseExecution").textContent = "⏸️ Pause";
            document.getElementById("liveRunStateBadge").textContent = "RUNNING";
        } else {
            await fetch(`${API_BASE}/api/timelapse/pause`, { method: "POST" });
            executionPaused = true;
            document.getElementById("btnPauseExecution").textContent = "▶️ Resume";
            document.getElementById("liveRunStateBadge").textContent = "PAUSED";
        }
    } catch (e) {}
}

async function cancelSequenceExecution() {
    try {
        await fetch(`${API_BASE}/api/timelapse/cancel`, { method: "POST" });
        executionActive = false;
        document.getElementById("btnStartExecution").disabled = false;
        document.getElementById("btnPauseExecution").disabled = true;
        document.getElementById("btnCancelExecution").disabled = true;
        document.getElementById("liveRunStateBadge").textContent = "CANCELLED";
    } catch (e) {}
}

function updateTimelapseTelemetry(tl) {
    if (!tl) return;

    if (tl.state === "RUNNING" || tl.state === "PAUSED") {
        executionActive = true;
        const currentShot = tl.current_shot ?? 0;
        const totalShots = tl.total_shots ?? 20;
        const pct = totalShots > 0 ? Math.floor((currentShot / totalShots) * 100) : 0;

        document.getElementById("execProgressBar").style.width = `${pct}%`;
        document.getElementById("execProgressPct").textContent = `${pct}%`;
        document.getElementById("execCurrentShot").textContent = `${currentShot} / ${totalShots}`;

        if (executionStartTime) {
            const elapsed = Math.floor((Date.now() - executionStartTime) / 1000);
            const em = Math.floor(elapsed / 60).toString().padStart(2, "0");
            const es = (elapsed % 60).toString().padStart(2, "0");
            document.getElementById("execElapsed").textContent = `${em}:${es}`;

            if (currentShot > 0) {
                const remaining = Math.max(0, Math.floor((elapsed / currentShot) * (totalShots - currentShot)));
                const rm = Math.floor(remaining / 60).toString().padStart(2, "0");
                const rs = (remaining % 60).toString().padStart(2, "0");
                document.getElementById("execRemaining").textContent = `${rm}:${rs}`;
            }
        }

        // Fetch latest preview image into live gallery
        fetchLatestCapturedPreview(currentShot);
    } else if (tl.state === "COMPLETED") {
        if (executionActive) {
            executionActive = false;
            document.getElementById("btnStartExecution").disabled = false;
            document.getElementById("btnPauseExecution").disabled = true;
            document.getElementById("btnCancelExecution").disabled = true;
            document.getElementById("liveRunStateBadge").textContent = "COMPLETED";
            document.getElementById("liveRunStateBadge").className = "badge success";
            document.getElementById("execProgressBar").style.width = "100%";
            document.getElementById("execProgressPct").textContent = "100%";
        }
    }
}

let lastCapturedShotIndex = -1;
async function fetchLatestCapturedPreview(shotIndex) {
    if (shotIndex <= lastCapturedShotIndex || shotIndex <= 0) return;
    lastCapturedShotIndex = shotIndex;

    const gallery = document.getElementById("execLiveGallery");
    const placeholder = document.getElementById("galleryEmptyPlaceholder");
    if (placeholder) placeholder.style.display = "none";

    const item = document.createElement("div");
    item.className = "gallery-item";
    const imgUrl = `${API_BASE}/api/camera/preview/latest?t=${Date.now()}`;

    item.innerHTML = `
        <img class="gallery-thumb" src="${imgUrl}" alt="Frame ${shotIndex}">
        <div class="gallery-info">
            <span class="gallery-title">Shot #${shotIndex}</span>
            <span class="gallery-sub">Pan: ${latestPan.toFixed(1)}°</span>
        </div>
    `;
    item.onclick = () => openImageZoomModal(imgUrl, `Captured Frame #${shotIndex}`);

    if (gallery) {
        gallery.insertBefore(item, gallery.firstChild);
    }

    const countEl = document.getElementById("execPhotoCount");
    if (countEl) countEl.textContent = `${shotIndex} frames captured`;
}

function openImageZoomModal(imgUrl, title) {
    const modal = document.getElementById("imageZoomModal");
    const img = document.getElementById("zoomImage");
    const titleEl = document.getElementById("zoomImageTitle");
    if (modal && img) {
        img.src = imgUrl;
        if (titleEl) titleEl.textContent = title;
        modal.classList.remove("hidden");
    }
}

function closeImageZoomModal() {
    const modal = document.getElementById("imageZoomModal");
    if (modal) modal.classList.add("hidden");
}

// ==========================================================================
// 9. Startup & Initialization
// ==========================================================================

window.addEventListener("DOMContentLoaded", async () => {
    initSSE();
    await loadPlansList();
    goToStep(1);

    // Initial camera choices load
    try {
        const res = await fetch(`${API_BASE}/api/camera/config/choices`);
        if (res.ok) {
            const data = await res.json();
            if (data.choices) {
                populateChoicesDropdown("acqIso", data.choices.iso);
                populateChoicesDropdown("acqShutter", data.choices.shutter_speed);
                populateChoicesDropdown("acqAperture", data.choices.aperture);
            }
        }
    } catch (e) {}
});

function populateChoicesDropdown(elemId, choices) {
    if (!choices || choices.length === 0) return;
    const sel = document.getElementById(elemId);
    if (!sel) return;
    const currVal = sel.value;
    sel.innerHTML = "";
    choices.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        if (c === currVal) opt.selected = true;
        sel.appendChild(opt);
    });
}
