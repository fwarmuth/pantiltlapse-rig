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
let currentPanKeyframes = [
    { progress: 0.0, value: 0.0, outgoing_mode: "smooth", tangent_scale: 1.0 },
    { progress: 1.0, value: 45.0, outgoing_mode: "smooth", tangent_scale: 1.0 }
];
let currentTiltKeyframes = [
    { progress: 0.0, value: 0.0, outgoing_mode: "smooth", tangent_scale: 1.0 },
    { progress: 1.0, value: 15.0, outgoing_mode: "smooth", tangent_scale: 1.0 }
];
let activeTrackTab = "pan"; // "pan" | "tilt"
let selectedTrack = "pan";
let selectedKeyframeIndex = 0;
let curveFilter = "all";
let curveDragState = null;
let dryRunProgressPct = 0;

// Live View & Post-Processing State
let isLiveViewActive = false;
let liveViewFps = 0.0;
let lastFrameTime = performance.now();
let streamPollingTimer = null;
let enhancementEnabled = true;
let enhanceMode = "none";
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
        setupCurveEventListeners();
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

async function reconnectCamera() {
    try {
        const res = await fetch(`${API_BASE}/api/camera/reconnect`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            alert(data.message || "Camera connected successfully!");
            await pollStatus();
        } else {
            alert(data.detail?.message || "Failed to reconnect camera. Ensure camera is powered on and awake.");
        }
    } catch (err) {
        alert("Camera reconnection failed: " + err.message);
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

let isEnlargedLiveViewOpen = false;

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
            const btnEnlarged = document.getElementById("btnEnlargedToggleStream");
            if (btnEnlarged) btnEnlarged.textContent = "⏹ Stop Stream";
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
    const btnEnlarged = document.getElementById("btnEnlargedToggleStream");
    if (btnEnlarged) btnEnlarged.textContent = "▶ Start Stream";
    document.getElementById("streamPlaceholder").classList.remove("hidden");
    document.getElementById("streamState").textContent = "IDLE";
    document.getElementById("streamFps").textContent = "0.0";
    const fpsBadge = document.getElementById("enlargedStreamFpsBadge");
    if (fpsBadge) fpsBadge.textContent = "0.0 FPS";
}

async function runFrameFetchLoop() {
    const canvas = document.getElementById("canvasEnhancedPreview");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    
    const enlargedCanvas = document.getElementById("canvasEnlargedLiveView");
    const enlargedCtx = enlargedCanvas ? enlargedCanvas.getContext("2d", { willReadFrequently: true }) : null;

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
                        const resBadge = document.getElementById("enlargedStreamResBadge");
                        if (resBadge) resBadge.textContent = `${canvas.width}×${canvas.height}`;
                    }

                    if (enlargedCanvas && (enlargedCanvas.width !== bitmap.width || enlargedCanvas.height !== bitmap.height)) {
                        enlargedCanvas.width = bitmap.width;
                        enlargedCanvas.height = bitmap.height;
                    }

                    ctx.drawImage(bitmap, 0, 0);
                    bitmap.close();

                    if (enhanceMode !== "none") {
                        const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
                        applyImageEnhancement(imgData, enhanceMode, filterGain, filterContrast, filterClipLimit);
                        ctx.putImageData(imgData, 0, 0);
                    }

                    // If enlarged modal is active, mirror or crop/zoom to enlarged canvas
                    if (isEnlargedLiveViewOpen && enlargedCtx && enlargedCanvas) {
                        if (!focusZoomEnabled) {
                            // 1x Full Frame View
                            enlargedCtx.drawImage(canvas, 0, 0, enlargedCanvas.width, enlargedCanvas.height);
                        } else {
                            // 5x Focus Zoom Loupe View
                            const srcW = canvas.width;
                            const srcH = canvas.height;
                            const cropW = srcW / focusZoomFactor;
                            const cropH = srcH / focusZoomFactor;

                            const cropX = Math.max(0, Math.min(srcW - cropW, (focusCenterX * srcW) - (cropW / 2)));
                            const cropY = Math.max(0, Math.min(srcH - cropH, (focusCenterY * srcH) - (cropH / 2)));

                            // Draw 5x magnified region
                            enlargedCtx.drawImage(canvas, cropX, cropY, cropW, cropH, 0, 0, enlargedCanvas.width, enlargedCanvas.height);

                            // Draw Focus Center Crosshair
                            const midX = enlargedCanvas.width / 2;
                            const midY = enlargedCanvas.height / 2;
                            enlargedCtx.save();
                            enlargedCtx.strokeStyle = "rgba(56, 189, 248, 0.85)";
                            enlargedCtx.lineWidth = 1.5;

                            enlargedCtx.beginPath();
                            enlargedCtx.moveTo(midX - 26, midY);
                            enlargedCtx.lineTo(midX + 26, midY);
                            enlargedCtx.moveTo(midX, midY - 26);
                            enlargedCtx.lineTo(midX, midY + 26);
                            enlargedCtx.stroke();

                            enlargedCtx.beginPath();
                            enlargedCtx.arc(midX, midY, 14, 0, 2 * Math.PI);
                            enlargedCtx.stroke();

                            // Draw Mini Picture-in-Picture (PiP) Navigator Box in bottom-left
                            const pipW = 110;
                            const pipH = Math.round(pipW * (srcH / srcW));
                            const pipX = 14;
                            const pipY = enlargedCanvas.height - pipH - 14;

                            enlargedCtx.fillStyle = "rgba(15, 23, 42, 0.85)";
                            enlargedCtx.fillRect(pipX - 2, pipY - 2, pipW + 4, pipH + 4);
                            enlargedCtx.drawImage(canvas, pipX, pipY, pipW, pipH);
                            enlargedCtx.strokeStyle = "rgba(255, 255, 255, 0.35)";
                            enlargedCtx.strokeRect(pipX, pipY, pipW, pipH);

                            // PiP Crop indicator bounding box
                            const boxX = pipX + (cropX / srcW) * pipW;
                            const boxY = pipY + (cropY / srcH) * pipH;
                            const boxW = (cropW / srcW) * pipW;
                            const boxH = (cropH / srcH) * pipH;
                            enlargedCtx.strokeStyle = "#38bdf8";
                            enlargedCtx.lineWidth = 1.5;
                            enlargedCtx.strokeRect(boxX, boxY, boxW, boxH);
                            enlargedCtx.restore();
                        }
                        updateEnlargedLiveHud();
                    }

                    drawHistogramFromCanvas(canvas);

                    // Measured FPS
                    const now = performance.now();
                    const delta = now - lastFrameTime;
                    lastFrameTime = now;
                    if (delta > 0) {
                        liveViewFps = 0.8 * liveViewFps + 0.2 * (1000 / delta);
                        document.getElementById("streamFps").textContent = liveViewFps.toFixed(1);
                        const fpsBadge = document.getElementById("enlargedStreamFpsBadge");
                        if (fpsBadge) fpsBadge.textContent = `${liveViewFps.toFixed(1)} FPS`;
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

// --------------------------------------------------------------------------
// 5x Focus Zoom & Focus Stepping Controller
// --------------------------------------------------------------------------

let focusZoomEnabled = false;
let focusZoomFactor = 5.0;
let focusCenterX = 0.5; // normalized 0..1
let focusCenterY = 0.5;
let isFocusStepping = false;
let enlargedCanvasClickInitialized = false;

function initEnlargedCanvasClick() {
    if (enlargedCanvasClickInitialized) return;
    enlargedCanvasClickInitialized = true;

    const canvas = document.getElementById("canvasEnlargedLiveView");
    if (!canvas) return;

    canvas.addEventListener("click", (e) => {
        const rect = canvas.getBoundingClientRect();
        const clickNormX = (e.clientX - rect.left) / rect.width;
        const clickNormY = (e.clientY - rect.top) / rect.height;

        if (!focusZoomEnabled) {
            // Click to activate 5x Focus Zoom centered at clicked coordinates
            focusZoomEnabled = true;
            focusCenterX = Math.max(0.1, Math.min(0.9, clickNormX));
            focusCenterY = Math.max(0.1, Math.min(0.9, clickNormY));
            updateFocusZoomUI();
        } else {
            // User clicked inside 5x zoomed view - translate position to full frame
            const cropWNorm = 1.0 / focusZoomFactor;
            const cropHNorm = 1.0 / focusZoomFactor;
            const startX = Math.max(0, Math.min(1.0 - cropWNorm, focusCenterX - cropWNorm / 2));
            const startY = Math.max(0, Math.min(1.0 - cropHNorm, focusCenterY - cropHNorm / 2));

            const newCenterX = startX + (clickNormX * cropWNorm);
            const newCenterY = startY + (clickNormY * cropHNorm);
            focusCenterX = Math.max(0.1, Math.min(0.9, newCenterX));
            focusCenterY = Math.max(0.1, Math.min(0.9, newCenterY));
        }
    });
}

function toggleFocusZoom() {
    focusZoomEnabled = !focusZoomEnabled;
    updateFocusZoomUI();
}

function resetFocusZoom() {
    focusZoomEnabled = false;
    focusCenterX = 0.5;
    focusCenterY = 0.5;
    updateFocusZoomUI();
}

function updateFocusZoomUI() {
    const btnToggle = document.getElementById("btnToggleFocusZoom");
    const btnReset = document.getElementById("btnResetFocusZoom");
    const badge = document.getElementById("focusZoomOverlayBadge");
    const canvas = document.getElementById("canvasEnlargedLiveView");

    if (btnToggle) {
        if (focusZoomEnabled) {
            btnToggle.classList.add("btn-focus-active");
            btnToggle.textContent = "🔍 5x Zoom ON";
        } else {
            btnToggle.classList.remove("btn-focus-active");
            btnToggle.textContent = "🔍 5x Focus Loupe";
        }
    }
    if (btnReset) {
        if (focusZoomEnabled) {
            btnReset.classList.remove("hidden");
        } else {
            btnReset.classList.add("hidden");
        }
    }
    if (badge) {
        if (focusZoomEnabled) {
            badge.classList.remove("hidden");
        } else {
            badge.classList.add("hidden");
        }
    }
    if (canvas) {
        canvas.style.cursor = focusZoomEnabled ? "crosshair" : "zoom-in";
    }
}

async function driveCameraFocus(direction, stepSize) {
    if (isFocusStepping) return;
    isFocusStepping = true;
    const statusEl = document.getElementById("lblFocusStatus");
    if (statusEl) statusEl.textContent = `Stepping ${direction.toUpperCase()} ${stepSize}...`;

    try {
        const res = await fetch(`${API_BASE}/api/camera/focus/step`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ direction, step_size: stepSize })
        });
        const data = await res.json();
        if (res.ok) {
            if (statusEl) statusEl.textContent = `${direction.toUpperCase()} ${stepSize} OK`;
        } else {
            if (statusEl) statusEl.textContent = "Focus Err";
            console.warn("Focus step failed:", data);
        }
    } catch (e) {
        console.error("Focus step error:", e);
        if (statusEl) statusEl.textContent = "Error";
    } finally {
        isFocusStepping = false;
        setTimeout(() => {
            if (statusEl && statusEl.textContent.includes("OK")) {
                statusEl.textContent = "Idle";
            }
        }, 1500);
    }
}

async function triggerCameraAutofocus() {
    const statusEl = document.getElementById("lblFocusStatus");
    if (statusEl) statusEl.textContent = "Autofocusing...";

    try {
        const res = await fetch(`${API_BASE}/api/camera/focus/autofocus`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            if (statusEl) statusEl.textContent = "AF Locked";
        } else {
            if (statusEl) statusEl.textContent = "AF Failed";
            alert(data.detail?.message || "Autofocus failed");
        }
    } catch (e) {
        if (statusEl) statusEl.textContent = "AF Error";
    } finally {
        setTimeout(() => {
            if (statusEl && statusEl.textContent.includes("AF Locked")) {
                statusEl.textContent = "Idle";
            }
        }, 1500);
    }
}

function openEnlargedLiveViewModal() {
    isEnlargedLiveViewOpen = true;
    initEnlargedCanvasClick();
    const modal = document.getElementById("enlargedLiveViewModal");
    if (modal) modal.classList.remove("hidden");

    // Sync filter controls to enlarged toolbar
    const selEnlarged = document.getElementById("selEnlargedEnhanceMode");
    const sGain = document.getElementById("sliderEnlargedGain");
    const sContrast = document.getElementById("sliderEnlargedContrast");
    if (selEnlarged) selEnlarged.value = enhanceMode;
    if (sGain) sGain.value = filterGain;
    if (sContrast) sContrast.value = filterContrast;
    
    const lblG = document.getElementById("lblValEnlargedGain");
    const lblC = document.getElementById("lblValEnlargedContrast");
    if (lblG) lblG.textContent = `${filterGain.toFixed(1)}x`;
    if (lblC) lblC.textContent = `${filterContrast.toFixed(1)}x`;

    updateFocusZoomUI();
    updateEnlargedLiveHud();

    // Auto-start stream if idle
    if (!isLiveViewActive) {
        startLiveView();
    }
}

function closeEnlargedLiveViewModal() {
    isEnlargedLiveViewOpen = false;
    resetFocusZoom();
    const modal = document.getElementById("enlargedLiveViewModal");
    if (modal) modal.classList.add("hidden");
}

function updateEnlargedLiveHud() {
    const hudPan = document.getElementById("enlargedHudPan");
    const hudTilt = document.getElementById("enlargedHudTilt");
    if (hudPan) hudPan.textContent = `${typeof latestPan === 'number' ? latestPan.toFixed(2) : 0.00}°`;
    if (hudTilt) hudTilt.textContent = `${typeof latestTilt === 'number' ? latestTilt.toFixed(2) : 0.00}°`;
}

function syncEnhanceModeFromEnlarged(val) {
    enhanceMode = val;
    const sel = document.getElementById("selEnhanceMode");
    if (sel) sel.value = val;
}

function syncGainFromEnlarged(val) {
    filterGain = parseFloat(val);
    const slider = document.getElementById("sliderGain");
    const lbl = document.getElementById("lblValGain");
    const lblEnlarged = document.getElementById("lblValEnlargedGain");
    if (slider) slider.value = val;
    if (lbl) lbl.textContent = `${filterGain.toFixed(1)}x`;
    if (lblEnlarged) lblEnlarged.textContent = `${filterGain.toFixed(1)}x`;
}

function syncContrastFromEnlarged(val) {
    filterContrast = parseFloat(val);
    const slider = document.getElementById("sliderContrast");
    const lbl = document.getElementById("lblValContrast");
    const lblEnlarged = document.getElementById("lblValEnlargedContrast");
    if (slider) slider.value = val;
    if (lbl) lbl.textContent = `${filterContrast.toFixed(1)}x`;
    if (lblEnlarged) lblEnlarged.textContent = `${filterContrast.toFixed(1)}x`;
}

async function triggerPlanTestShotFromEnlarged() {
    await triggerPlanTestShot();
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

    // Mirror to enlarged controls
    const selEnlarged = document.getElementById("selEnlargedEnhanceMode");
    const sGainEnlarged = document.getElementById("sliderEnlargedGain");
    const sContrastEnlarged = document.getElementById("sliderEnlargedContrast");
    if (selEnlarged) selEnlarged.value = enhanceMode;
    if (sGainEnlarged) sGainEnlarged.value = filterGain;
    if (sContrastEnlarged) sContrastEnlarged.value = filterContrast;
}

/**
 * High-performance client-side image processing for low-light camera framing.
 * Includes CLAHE (Contrast Limited Adaptive Histogram Equalization), Gain/Gamma boost, Edge detect, and Passthrough.
 */
function applyImageEnhancement(imageData, mode, gain, contrast, clipLimit) {
    if (mode === "none") return;
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
            currentPanKeyframes = JSON.parse(JSON.stringify(activePlan.trajectory.pan_keyframes || []));
            currentTiltKeyframes = JSON.parse(JSON.stringify(activePlan.trajectory.tilt_keyframes || []));
            syncPlanInputs();
            renderKeyframeTable();
            updateTrajectoryPreview();
        }
    } catch (e) {
        console.error("Load plan detail error:", e);
    }
}

function generateUUID() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID();
    }
    if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
        return ([1e7]+-1e3+-4e3+-8e3+-1e11).replace(/[018]/g, c =>
            (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4).toString(16)
        );
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function(c) {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}

function createNewPlan() {
    activePlan = {
        id: generateUUID(),
        revision: 1,
        name: "New Time-lapse Sequence",
        description: "",
        trajectory: {
            pan_keyframes: [
                { progress: 0.0, value: 0.0, outgoing_mode: "smooth", tangent_scale: 1.0 },
                { progress: 1.0, value: 45.0, outgoing_mode: "smooth", tangent_scale: 1.0 }
            ],
            tilt_keyframes: [
                { progress: 0.0, value: 0.0, outgoing_mode: "smooth", tangent_scale: 1.0 },
                { progress: 1.0, value: 15.0, outgoing_mode: "smooth", tangent_scale: 1.0 }
            ]
        },
        schedule: { total_shots: 24, interval_s: 5.0, settle_time_s: 0.5 },
        acquisition: { iso: "400", shutter_speed: "1/125", aperture: "5.6", camera_format: "JPEG" },
        preview: { iso: "3200", shutter_speed: "1/4", aperture: "2.8" }
    };
    currentPanKeyframes = JSON.parse(JSON.stringify(activePlan.trajectory.pan_keyframes));
    currentTiltKeyframes = JSON.parse(JSON.stringify(activePlan.trajectory.tilt_keyframes));
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
    document.getElementById("lblPlanKeyframeCount").textContent = `${currentPanKeyframes.length} Pan / ${currentTiltKeyframes.length} Tilt`;
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

    activePlan.trajectory = {
        pan_keyframes: currentPanKeyframes,
        tilt_keyframes: currentTiltKeyframes
    };

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
            let errorMsg = "Failed to save plan";
            if (saved && saved.detail) {
                if (typeof saved.detail === "string") {
                    errorMsg = saved.detail;
                } else if (saved.detail.message) {
                    errorMsg = saved.detail.message;
                } else if (Array.isArray(saved.detail)) {
                    errorMsg = saved.detail.map(d => (d.loc ? d.loc.join(".") + ": " : "") + d.msg).join("\n");
                }
            }
            alert(`❌ Save Failed: ${errorMsg}`);
        }
    } catch (e) {
        console.error("Save plan error:", e);
        alert(`❌ Network or server error while saving plan: ${e.message}`);
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

function switchTrackTab(track) {
    activeTrackTab = track;
    document.getElementById("tabTrackPan")?.classList.toggle("active", track === "pan");
    document.getElementById("tabTrackTilt")?.classList.toggle("active", track === "tilt");

    const lblCap = document.getElementById("lblActiveTrackCap");
    const lblAdd = document.getElementById("lblActiveTrackAdd");
    if (lblCap) lblCap.textContent = track === "pan" ? "Pan" : "Tilt";
    if (lblAdd) lblAdd.textContent = track === "pan" ? "Pan Track" : "Tilt Track";

    // Auto-select first keyframe on this track if switching
    if (selectedTrack !== track) {
        selectedTrack = track;
        selectedKeyframeIndex = 0;
    }

    renderKeyframeTable();
    updateTrajectoryPreview();
}

function setCurveFilter(filter) {
    curveFilter = filter;
    document.getElementById("btnFilterAll")?.classList.toggle("active", filter === "all");
    document.getElementById("btnFilterPan")?.classList.toggle("active", filter === "pan");
    document.getElementById("btnFilterTilt")?.classList.toggle("active", filter === "tilt");
    updateTrajectoryPreview();
}

function selectKeyframe(track, idx) {
    const list = track === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    if (idx < 0 || idx >= list.length) return;
    selectedTrack = track;
    selectedKeyframeIndex = idx;

    // If active track tab differs, switch to show the table
    if (activeTrackTab !== track) {
        activeTrackTab = track;
        document.getElementById("tabTrackPan")?.classList.toggle("active", track === "pan");
        document.getElementById("tabTrackTilt")?.classList.toggle("active", track === "tilt");
        const lblCap = document.getElementById("lblActiveTrackCap");
        const lblAdd = document.getElementById("lblActiveTrackAdd");
        if (lblCap) lblCap.textContent = track === "pan" ? "Pan" : "Tilt";
        if (lblAdd) lblAdd.textContent = track === "pan" ? "Pan Track" : "Tilt Track";
    }

    renderKeyframeTable();
    updateInspectorUI();
    updateTrajectoryPreview();
}

function updateInspectorUI() {
    const list = selectedTrack === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    const kf = list[selectedKeyframeIndex];
    if (!kf) return;

    const isStart = selectedKeyframeIndex === 0;
    const isEnd = selectedKeyframeIndex === list.length - 1;
    const trackColor = selectedTrack === "pan" ? "#38bdf8" : "#34d399";
    const trackName = selectedTrack === "pan" ? "PAN" : "TILT";

    const labelEl = document.getElementById("inspLabel");
    const timeEl = document.getElementById("inspTime");
    const panEl = document.getElementById("inspPan");
    const tiltEl = document.getElementById("inspTilt");
    const progEl = document.getElementById("inspProgress");
    const modeEl = document.getElementById("inspMode");
    const delBtn = document.getElementById("btnInspDelete");

    if (labelEl) {
        labelEl.innerHTML = `<span style="color:${trackColor}; font-weight:bold;">[${trackName}]</span> ` + 
            (isStart ? `Waypoint #1 (Start)` : (isEnd ? `Waypoint #${list.length} (End)` : `Waypoint #${selectedKeyframeIndex + 1}`));
    }
    if (timeEl) {
        timeEl.textContent = `Progress: t = ${kf.progress.toFixed(2)} (${(kf.progress * 100).toFixed(0)}%)`;
    }
    if (panEl) panEl.value = (selectedTrack === "pan" ? kf.value : (currentPanKeyframes[0]?.value || 0)).toFixed(1);
    if (tiltEl) tiltEl.value = (selectedTrack === "tilt" ? kf.value : (currentTiltKeyframes[0]?.value || 0)).toFixed(1);
    if (progEl) {
        progEl.value = kf.progress.toFixed(2);
        progEl.disabled = isStart || isEnd;
    }
    if (modeEl) modeEl.value = kf.outgoing_mode || "smooth";
    if (delBtn) delBtn.style.display = (isStart || isEnd) ? "none" : "inline-flex";
}

function onInspectorChange(param, val) {
    const list = selectedTrack === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    const kf = list[selectedKeyframeIndex];
    if (!kf) return;

    if (param === "pan" && selectedTrack === "pan") {
        kf.value = parseFloat(val) || 0.0;
    } else if (param === "tilt" && selectedTrack === "tilt") {
        kf.value = Math.max(0, Math.min(80, parseFloat(val) || 0.0));
    } else if (param === "progress") {
        if (selectedKeyframeIndex > 0 && selectedKeyframeIndex < list.length - 1) {
            const prevP = list[selectedKeyframeIndex - 1].progress;
            const nextP = list[selectedKeyframeIndex + 1].progress;
            kf.progress = Math.max(prevP + 0.01, Math.min(nextP - 0.01, parseFloat(val) || 0.5));
        }
    } else if (param === "mode") {
        kf.outgoing_mode = val;
    }

    renderKeyframeTable();
    updateTrajectoryPreview();
}

function visitSelectedKeyframePose() {
    const list = selectedTrack === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    const kf = list[selectedKeyframeIndex];
    if (!kf) return;
    if (selectedTrack === "pan") {
        moveAbsolute(kf.value, latestTilt);
    } else {
        moveAbsolute(latestPan, kf.value);
    }
}

function overwriteSelectedKeyframePose() {
    const list = selectedTrack === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    const kf = list[selectedKeyframeIndex];
    if (!kf) return;
    kf.value = selectedTrack === "pan" ? latestPan : Math.max(0, Math.min(80, latestTilt));
    renderKeyframeTable();
    updateTrajectoryPreview();
}

function deleteSelectedKeyframe() {
    deleteKeyframe(selectedTrack, selectedKeyframeIndex);
}

function renderKeyframeTable() {
    const tbody = document.getElementById("keyframeTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";

    // Sort both tracks by progress
    currentPanKeyframes.sort((a, b) => a.progress - b.progress);
    if (currentPanKeyframes.length > 0) currentPanKeyframes[0].progress = 0.0;
    if (currentPanKeyframes.length > 1) currentPanKeyframes[currentPanKeyframes.length - 1].progress = 1.0;

    currentTiltKeyframes.sort((a, b) => a.progress - b.progress);
    if (currentTiltKeyframes.length > 0) currentTiltKeyframes[0].progress = 0.0;
    if (currentTiltKeyframes.length > 1) currentTiltKeyframes[currentTiltKeyframes.length - 1].progress = 1.0;

    // Update count badges
    const panCountEl = document.getElementById("panCount");
    const tiltCountEl = document.getElementById("tiltCount");
    if (panCountEl) panCountEl.textContent = currentPanKeyframes.length;
    if (tiltCountEl) tiltCountEl.textContent = currentTiltKeyframes.length;

    const list = activeTrackTab === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    if (selectedTrack === activeTrackTab && selectedKeyframeIndex >= list.length) {
        selectedKeyframeIndex = Math.max(0, list.length - 1);
    }

    list.forEach((kf, idx) => {
        const tr = document.createElement("tr");
        const isStart = idx === 0;
        const isEnd = idx === list.length - 1;
        const isSelected = selectedTrack === activeTrackTab && idx === selectedKeyframeIndex;

        if (isSelected) {
            tr.classList.add("selected");
        }

        const badgeClass = isStart ? "start" : (isEnd ? "end" : "intermediate");
        const trackPrefix = activeTrackTab === "pan" ? "P" : "T";
        const badgeLabel = isStart ? `#${trackPrefix}1 START` : (isEnd ? `#${trackPrefix}${idx + 1} END` : `#${trackPrefix}${idx + 1} WAYPT`);

        tr.innerHTML = `
            <td>
                <span class="keyframe-badge ${badgeClass}">${badgeLabel}</span>
            </td>
            <td>
                <input type="number" step="0.02" min="0" max="1" value="${kf.progress.toFixed(2)}"
                    ${isStart || isEnd ? "disabled" : ""} 
                    onfocus="selectKeyframe('${activeTrackTab}', ${idx})"
                    onchange="onKeyframeProgressChange(${idx}, this.value)">
            </td>
            <td>
                <input type="number" step="0.5" value="${kf.value.toFixed(1)}"
                    onfocus="selectKeyframe('${activeTrackTab}', ${idx})"
                    onchange="onKeyframeValueChange(${idx}, this.value)">
            </td>
            <td>
                <select onchange="onKeyframeModeChange(${idx}, this.value)" onfocus="selectKeyframe('${activeTrackTab}', ${idx})" style="width:90px;">
                    <option value="smooth" ${kf.outgoing_mode === "smooth" ? "selected" : ""}>Smooth</option>
                    <option value="linear" ${kf.outgoing_mode === "linear" ? "selected" : ""}>Linear</option>
                </select>
            </td>
            <td>
                <button class="btn btn-secondary btn-xs" onclick="event.stopPropagation(); visitKeyframeAxis('${activeTrackTab}', ${idx})" title="Move ${activeTrackTab} axis to angle">🎯 Go</button>
                <button class="btn btn-accent btn-xs" onclick="event.stopPropagation(); overwriteKeyframeWithCurrent('${activeTrackTab}', ${idx})" title="Update with current rig angle">📍 Set</button>
                ${!isStart && !isEnd ? `<button class="btn btn-danger btn-xs" onclick="event.stopPropagation(); deleteKeyframe('${activeTrackTab}', ${idx})" title="Remove keyframe">✕</button>` : ""}
            </td>
        `;

        tr.addEventListener("click", (e) => {
            if (e.target.tagName !== "INPUT" && e.target.tagName !== "SELECT" && e.target.tagName !== "BUTTON") {
                selectKeyframe(activeTrackTab, idx);
            }
        });

        tbody.appendChild(tr);
    });

    updateInspectorUI();
}

function onKeyframeProgressChange(idx, val) {
    const list = activeTrackTab === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    if (idx === 0 || idx === list.length - 1) return;
    const prevP = list[idx - 1].progress;
    const nextP = list[idx + 1].progress;
    list[idx].progress = Math.max(prevP + 0.01, Math.min(nextP - 0.01, parseFloat(val) || 0.5));
    renderKeyframeTable();
    updateTrajectoryPreview();
}

function onKeyframeValueChange(idx, val) {
    const list = activeTrackTab === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    if (activeTrackTab === "pan") {
        list[idx].value = parseFloat(val) || 0.0;
    } else {
        list[idx].value = Math.max(0, Math.min(80, parseFloat(val) || 0.0));
    }
    updateTrajectoryPreview();
    updateInspectorUI();
}

function onKeyframeModeChange(idx, mode) {
    const list = activeTrackTab === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    list[idx].outgoing_mode = mode;
    updateTrajectoryPreview();
    updateInspectorUI();
}

function addCurrentAngleToActiveTrack() {
    const isPan = activeTrackTab === "pan";
    const currentAngle = isPan ? latestPan : Math.max(0, Math.min(80, latestTilt));
    const list = isPan ? currentPanKeyframes : currentTiltKeyframes;

    if (list.length === 2 && list[0].value === 0 && list[1].value === 0) {
        list[0].value = currentAngle;
        selectedKeyframeIndex = 0;
    } else {
        const newKf = {
            progress: 0.5,
            value: currentAngle,
            outgoing_mode: "smooth",
            tangent_scale: 1.0
        };
        list.push(newKf);
        list.sort((a, b) => a.progress - b.progress);
        selectedTrack = activeTrackTab;
        selectedKeyframeIndex = list.indexOf(newKf);
    }

    renderKeyframeTable();
    updateTrajectoryPreview();
}

function addNewIntermediateKeyframe() {
    const isPan = activeTrackTab === "pan";
    const list = isPan ? currentPanKeyframes : currentTiltKeyframes;

    let targetP = 0.5;
    if (list.length >= 2) {
        let maxGap = 0;
        let bestP = 0.5;
        for (let i = 0; i < list.length - 1; i++) {
            const gap = list[i + 1].progress - list[i].progress;
            if (gap > maxGap) {
                maxGap = gap;
                bestP = (list[i].progress + list[i + 1].progress) / 2;
            }
        }
        targetP = Math.round(bestP * 100) / 100;
    }

    const sampled = sampleTrackSpline(list, 100);
    let sampleVal = isPan ? latestPan : latestTilt;
    if (sampled.length > 0) {
        const sIdx = Math.min(sampled.length - 1, Math.floor(targetP * (sampled.length - 1)));
        sampleVal = sampled[sIdx].val;
    }

    const newKf = {
        progress: targetP,
        value: Math.round(sampleVal * 10) / 10,
        outgoing_mode: "smooth",
        tangent_scale: 1.0
    };
    list.push(newKf);
    list.sort((a, b) => a.progress - b.progress);
    selectedTrack = activeTrackTab;
    selectedKeyframeIndex = list.indexOf(newKf);

    renderKeyframeTable();
    updateTrajectoryPreview();
}

function overwriteKeyframeWithCurrent(track, idx) {
    const list = track === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    if (idx < 0 || idx >= list.length) return;
    list[idx].value = track === "pan" ? latestPan : Math.max(0, Math.min(80, latestTilt));
    renderKeyframeTable();
    updateTrajectoryPreview();
}

function visitKeyframeAxis(track, idx) {
    const list = track === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    if (idx < 0 || idx >= list.length) return;
    const kf = list[idx];
    if (track === "pan") {
        moveAbsolute(kf.value, latestTilt);
    } else {
        moveAbsolute(latestPan, kf.value);
    }
}

function deleteKeyframe(track, idx) {
    const list = track === "pan" ? currentPanKeyframes : currentTiltKeyframes;
    if (idx === 0 || idx === list.length - 1) return;
    list.splice(idx, 1);
    if (selectedTrack === track && selectedKeyframeIndex >= list.length) {
        selectedKeyframeIndex = list.length - 1;
    }
    renderKeyframeTable();
    updateTrajectoryPreview();
}

// --------------------------------------------------------------------------
// Hermite Spline Sampling Algorithm for Independent Axis Tracks
// --------------------------------------------------------------------------

function calculateTrackTangents(keyframes) {
    const num = keyframes.length;
    return keyframes.map((kf, i) => {
        const scale = kf.tangent_scale !== undefined ? kf.tangent_scale : 1.0;
        if (scale === 0.0) return 0.0;
        if (i === 0) {
            const dt = keyframes[1].progress - keyframes[0].progress;
            return dt > 0 ? ((keyframes[1].value - keyframes[0].value) / dt) * scale : 0.0;
        }
        if (i === num - 1) {
            const dt = keyframes[num - 1].progress - keyframes[num - 2].progress;
            return dt > 0 ? ((keyframes[num - 1].value - keyframes[num - 2].value) / dt) * scale : 0.0;
        }
        const dt = keyframes[i + 1].progress - keyframes[i - 1].progress;
        return dt > 0 ? ((keyframes[i + 1].value - keyframes[i - 1].value) / dt) * scale : 0.0;
    });
}

function sampleTrackSpline(keyframes, count) {
    if (!keyframes || keyframes.length === 0) return [];
    if (keyframes.length === 1) {
        return Array(count).fill({ val: keyframes[0].value, t: 0 });
    }

    const tangents = calculateTrackTangents(keyframes);
    const points = [];

    for (let i = 0; i < count; i++) {
        const t = count > 1 ? i / (count - 1) : 0.0;
        
        let seg = 0;
        for (let s = 0; s < keyframes.length - 1; s++) {
            if (keyframes[s].progress <= t) seg = s;
            if (keyframes[s + 1].progress >= t) break;
        }
        if (seg >= keyframes.length - 1) seg = keyframes.length - 2;

        const kfA = keyframes[seg];
        const kfB = keyframes[seg + 1];
        const h = kfB.progress - kfA.progress;
        const u = h > 0 ? Math.max(0, Math.min(1, (t - kfA.progress) / h)) : 0;

        if (kfA.outgoing_mode === "linear") {
            points.push({
                val: kfA.value + u * (kfB.value - kfA.value),
                t: t
            });
        } else {
            const h00 = 2 * Math.pow(u, 3) - 3 * Math.pow(u, 2) + 1;
            const h10 = Math.pow(u, 3) - 2 * Math.pow(u, 2) + u;
            const h01 = -2 * Math.pow(u, 3) + 3 * Math.pow(u, 2);
            const h11 = Math.pow(u, 3) - Math.pow(u, 2);

            const val = h00 * kfA.value + h10 * h * tangents[seg] + h01 * kfB.value + h11 * h * tangents[seg + 1];
            points.push({ val, t });
        }
    }
    return points;
}

// --------------------------------------------------------------------------
// Interactive SVG Trajectory Plot Drawing & View Update
// --------------------------------------------------------------------------

function updateTrajectoryPreview() {
    if (!currentPanKeyframes || currentPanKeyframes.length < 2 || !currentTiltKeyframes || currentTiltKeyframes.length < 2) return;
    const totalShots = parseInt(document.getElementById("planTotalShots")?.value, 10) || 20;

    // Sample high-density curve points for each track independently
    const sampledPan = sampleTrackSpline(currentPanKeyframes, 120);
    const sampledTilt = sampleTrackSpline(currentTiltKeyframes, 120);

    const svgW = 640;
    const svgH = 250;
    const padL = 55;
    const padR = 25;
    const padT = 25;
    const padB = 40;
    const plotW = svgW - padL - padR;
    const plotH = svgH - padT - padB;

    // Calculate dynamic degrees range across both tracks
    let minPan = Infinity, maxPan = -Infinity;
    let minTilt = Infinity, maxTilt = -Infinity;

    sampledPan.forEach(p => {
        if (p.val < minPan) minPan = p.val;
        if (p.val > maxPan) maxPan = p.val;
    });
    currentPanKeyframes.forEach(kf => {
        if (kf.value < minPan) minPan = kf.value;
        if (kf.value > maxPan) maxPan = kf.value;
    });

    sampledTilt.forEach(p => {
        if (p.val < minTilt) minTilt = p.val;
        if (p.val > maxTilt) maxTilt = p.val;
    });
    currentTiltKeyframes.forEach(kf => {
        if (kf.value < minTilt) minTilt = kf.value;
        if (kf.value > maxTilt) maxTilt = kf.value;
    });

    let degMin = Math.min(minPan, minTilt, 0);
    let degMax = Math.max(maxPan, maxTilt, 10);
    let degSpan = Math.max(20, degMax - degMin);
    let padDeg = degSpan * 0.12;
    let yMin = degMin - padDeg;
    let yMax = degMax + padDeg;
    let yRange = yMax - yMin;

    // Coordinate conversion closures
    const pToX = (p) => padL + Math.max(0, Math.min(1, p)) * plotW;
    const degToY = (d) => padT + plotH - ((d - yMin) / yRange) * plotH;

    // 1. Draw Grid & Axes
    const svgGrid = document.getElementById("svgGrid");
    const svgZero = document.getElementById("svgZeroLine");
    const svgAxes = document.getElementById("svgAxes");

    if (svgGrid) {
        let gridHtml = "";
        const ticksCount = 4;
        for (let i = 0; i <= ticksCount; i++) {
            const frac = i / ticksCount;
            const degVal = yMin + frac * yRange;
            const y = degToY(degVal);
            gridHtml += `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${svgW - padR}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,0.06)" stroke-dasharray="3 3"/>`;
        }
        const timeTicks = [0.0, 0.25, 0.5, 0.75, 1.0];
        timeTicks.forEach(t => {
            const x = pToX(t);
            gridHtml += `<line x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${padT + plotH}" stroke="rgba(255,255,255,0.06)" stroke-dasharray="3 3"/>`;
        });
        svgGrid.innerHTML = gridHtml;
    }

    if (svgZero) {
        if (0 >= yMin && 0 <= yMax) {
            const y0 = degToY(0);
            svgZero.innerHTML = `<line x1="${padL}" y1="${y0.toFixed(1)}" x2="${svgW - padR}" y2="${y0.toFixed(1)}" stroke="rgba(255,255,255,0.22)" stroke-dasharray="4 2"/>
                                 <text x="${padL - 6}" y="${(y0 + 3).toFixed(1)}" text-anchor="end" class="svg-axis-text" fill="#94a3b8">0°</text>`;
        } else {
            svgZero.innerHTML = "";
        }
    }

    if (svgAxes) {
        let axesHtml = "";
        const ticksCount = 4;
        for (let i = 0; i <= ticksCount; i++) {
            const frac = i / ticksCount;
            const degVal = yMin + frac * yRange;
            const y = degToY(degVal);
            if (Math.abs(degVal) > 1.0 || !(0 >= yMin && 0 <= yMax)) {
                axesHtml += `<text x="${padL - 8}" y="${(y + 3.5).toFixed(1)}" text-anchor="end" class="svg-axis-text">${degVal.toFixed(0)}°</text>`;
            }
        }
        const timeLabels = [
            { t: 0.0, label: "0% [t=0.0]" },
            { t: 0.25, label: "25%" },
            { t: 0.50, label: "50%" },
            { t: 0.75, label: "75%" },
            { t: 1.0, label: "100% [t=1.0]" }
        ];
        timeLabels.forEach(tl => {
            const x = pToX(tl.t);
            const shotNum = Math.max(1, Math.round(tl.t * (totalShots - 1) + 1));
            axesHtml += `<text x="${x.toFixed(1)}" y="${padT + plotH + 15}" text-anchor="middle" class="svg-axis-text">${tl.label}</text>`;
            axesHtml += `<text x="${x.toFixed(1)}" y="${padT + plotH + 28}" text-anchor="middle" class="svg-axis-text" fill="#475569" font-size="8.5">S#${shotNum}</text>`;
        });
        svgAxes.innerHTML = axesHtml;
    }

    // 2. Generate Curve Paths
    let panPathStr = "";
    let tiltPathStr = "";

    sampledPan.forEach((p, i) => {
        const x = pToX(p.t);
        const yPan = degToY(p.val);
        panPathStr += (i === 0 ? `M ${x.toFixed(1)} ${yPan.toFixed(1)}` : ` L ${x.toFixed(1)} ${yPan.toFixed(1)}`);
    });

    sampledTilt.forEach((p, i) => {
        const x = pToX(p.t);
        const yTilt = degToY(p.val);
        tiltPathStr += (i === 0 ? `M ${x.toFixed(1)} ${yTilt.toFixed(1)}` : ` L ${x.toFixed(1)} ${yTilt.toFixed(1)}`);
    });

    const pathPanEl = document.getElementById("pathPan");
    const pathTiltEl = document.getElementById("pathTilt");

    if (pathPanEl) {
        pathPanEl.setAttribute("d", panPathStr);
        pathPanEl.style.display = (curveFilter === "tilt") ? "none" : "block";
    }
    if (pathTiltEl) {
        pathTiltEl.setAttribute("d", tiltPathStr);
        pathTiltEl.style.display = (curveFilter === "pan") ? "none" : "block";
    }

    // 3. Generate Stems & Independent Waypoint Time Handles
    const svgStems = document.getElementById("svgStems");
    if (svgStems) {
        let stemsHtml = "";

        // Pan stems (Cyan)
        if (curveFilter !== "tilt") {
            currentPanKeyframes.forEach((kf, idx) => {
                const x = pToX(kf.progress);
                const isSel = selectedTrack === "pan" && idx === selectedKeyframeIndex;
                const stemColor = isSel ? "rgba(56, 189, 248, 0.7)" : "rgba(56, 189, 248, 0.25)";
                const tagBg = isSel ? "#0284c7" : "rgba(15, 23, 42, 0.9)";
                const tagBorder = isSel ? "#38bdf8" : "#0284c7";
                const isEndpoint = idx === 0 || idx === currentPanKeyframes.length - 1;

                stemsHtml += `
                    <g class="svg-stem-group" data-track="pan" data-kidx="${idx}">
                        <line x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${padT + plotH}" stroke="${stemColor}" stroke-dasharray="3 3" stroke-width="${isSel ? 1.5 : 1}"/>
                        <g class="svg-time-handle" data-track="pan" data-type="time" data-kidx="${idx}" style="cursor: ${isEndpoint ? 'pointer' : 'ew-resize'};">
                            <rect x="${(x - 22).toFixed(1)}" y="${padT + plotH + 4}" width="44" height="15" rx="3" fill="${tagBg}" stroke="${tagBorder}" stroke-width="1"/>
                            <text x="${x.toFixed(1)}" y="${padT + plotH + 15}" text-anchor="middle" font-size="8.5" font-family="monospace" font-weight="bold" fill="#38bdf8">
                                #P${idx + 1} ${(kf.progress * 100).toFixed(0)}%
                            </text>
                        </g>
                    </g>
                `;
            });
        }

        // Tilt stems (Emerald)
        if (curveFilter !== "pan") {
            currentTiltKeyframes.forEach((kf, idx) => {
                const x = pToX(kf.progress);
                const isSel = selectedTrack === "tilt" && idx === selectedKeyframeIndex;
                const stemColor = isSel ? "rgba(52, 211, 153, 0.7)" : "rgba(52, 211, 153, 0.25)";
                const tagBg = isSel ? "#059669" : "rgba(15, 23, 42, 0.9)";
                const tagBorder = isSel ? "#34d399" : "#059669";
                const isEndpoint = idx === 0 || idx === currentTiltKeyframes.length - 1;

                stemsHtml += `
                    <g class="svg-stem-group" data-track="tilt" data-kidx="${idx}">
                        <line x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${padT + plotH}" stroke="${stemColor}" stroke-dasharray="3 3" stroke-width="${isSel ? 1.5 : 1}"/>
                        <g class="svg-time-handle" data-track="tilt" data-type="time" data-kidx="${idx}" style="cursor: ${isEndpoint ? 'pointer' : 'ew-resize'};">
                            <rect x="${(x - 22).toFixed(1)}" y="${padT + plotH + 20}" width="44" height="15" rx="3" fill="${tagBg}" stroke="${tagBorder}" stroke-width="1"/>
                            <text x="${x.toFixed(1)}" y="${padT + plotH + 31}" text-anchor="middle" font-size="8.5" font-family="monospace" font-weight="bold" fill="#34d399">
                                #T${idx + 1} ${(kf.progress * 100).toFixed(0)}%
                            </text>
                        </g>
                    </g>
                `;
            });
        }

        svgStems.innerHTML = stemsHtml;
    }

    // 4. Generate Interactive Keyframe Nodes
    const svgNodes = document.getElementById("svgNodes");
    if (svgNodes) {
        let nodesHtml = "";

        // Pan Nodes (Cyan)
        if (curveFilter !== "tilt") {
            currentPanKeyframes.forEach((kf, idx) => {
                const x = pToX(kf.progress);
                const yPan = degToY(kf.value);
                const isSel = selectedTrack === "pan" && idx === selectedKeyframeIndex;

                nodesHtml += `
                    <g class="svg-node-group" data-track="pan" data-type="pan" data-kidx="${idx}">
                        ${isSel ? `<circle cx="${x.toFixed(1)}" cy="${yPan.toFixed(1)}" r="11" fill="none" stroke="#38bdf8" stroke-width="2" stroke-dasharray="3 2" opacity="0.9"/>` : ""}
                        <circle cx="${x.toFixed(1)}" cy="${yPan.toFixed(1)}" r="15" fill="transparent" class="svg-curve-node" data-track="pan" data-type="pan" data-kidx="${idx}"/>
                        <circle cx="${x.toFixed(1)}" cy="${yPan.toFixed(1)}" r="${isSel ? 7 : 5.5}" fill="#38bdf8" stroke="#020617" stroke-width="2"/>
                        <text x="${x.toFixed(1)}" y="${(yPan - 9).toFixed(1)}" text-anchor="middle" font-size="8.5" font-family="monospace" font-weight="bold" fill="#38bdf8">
                            ${kf.value.toFixed(1)}°
                        </text>
                    </g>
                `;
            });
        }

        // Tilt Nodes (Emerald)
        if (curveFilter !== "pan") {
            currentTiltKeyframes.forEach((kf, idx) => {
                const x = pToX(kf.progress);
                const yTilt = degToY(kf.value);
                const isSel = selectedTrack === "tilt" && idx === selectedKeyframeIndex;

                nodesHtml += `
                    <g class="svg-node-group" data-track="tilt" data-type="tilt" data-kidx="${idx}">
                        ${isSel ? `<circle cx="${x.toFixed(1)}" cy="${yTilt.toFixed(1)}" r="11" fill="none" stroke="#34d399" stroke-width="2" stroke-dasharray="3 2" opacity="0.9"/>` : ""}
                        <circle cx="${x.toFixed(1)}" cy="${yTilt.toFixed(1)}" r="15" fill="transparent" class="svg-curve-node" data-track="tilt" data-type="tilt" data-kidx="${idx}"/>
                        <circle cx="${x.toFixed(1)}" cy="${yTilt.toFixed(1)}" r="${isSel ? 7 : 5.5}" fill="#34d399" stroke="#020617" stroke-width="2"/>
                        <text x="${x.toFixed(1)}" y="${(yTilt - 9).toFixed(1)}" text-anchor="middle" font-size="8.5" font-family="monospace" font-weight="bold" fill="#34d399">
                            ${kf.value.toFixed(1)}°
                        </text>
                    </g>
                `;
            });
        }

        svgNodes.innerHTML = nodesHtml;
    }

    // 5. Rehearsal Playhead Marker
    const svgPlayhead = document.getElementById("svgPlayhead");
    if (svgPlayhead) {
        if (dryRunActive && dryRunProgressPct > 0) {
            const playX = pToX(dryRunProgressPct / 100);
            svgPlayhead.style.display = "block";
            svgPlayhead.innerHTML = `
                <line x1="${playX.toFixed(1)}" y1="${padT}" x2="${playX.toFixed(1)}" y2="${padT + plotH}" stroke="#f59e0b" stroke-width="2"/>
                <polygon points="${(playX - 5).toFixed(1)},${padT} ${(playX + 5).toFixed(1)},${padT} ${playX.toFixed(1)},${padT + 8}" fill="#f59e0b"/>
            `;
        } else {
            svgPlayhead.style.display = "none";
        }
    }

    // 6. Diagnostics Text
    const diag = document.getElementById("plotDiagnostics");
    if (diag) {
        diag.textContent = `ΔPan: ${(maxPan - minPan).toFixed(1)}° | ΔTilt: ${(maxTilt - minTilt).toFixed(1)}° | Shots: ${totalShots}`;
    }

    updateTimingCalculations();
}

// --------------------------------------------------------------------------
// Direct Manipulation & Drag-and-Drop Controller (Adobe Premiere Style)
// --------------------------------------------------------------------------

function setupCurveEventListeners() {
    const svg = document.getElementById("svgPlot");
    const tooltip = document.getElementById("curveTooltip");
    if (!svg || svg.dataset.listenerAttached) return;
    svg.dataset.listenerAttached = "true";

    const getSvgCoords = (e) => {
        const pt = svg.createSVGPoint();
        pt.x = e.clientX;
        pt.y = e.clientY;
        return pt.matrixTransform(svg.getScreenCTM().inverse());
    };

    const getBounds = () => {
        const sampledPan = sampleTrackSpline(currentPanKeyframes, 100);
        const sampledTilt = sampleTrackSpline(currentTiltKeyframes, 100);
        let minPan = Infinity, maxPan = -Infinity;
        let minTilt = Infinity, maxTilt = -Infinity;

        sampledPan.forEach(p => {
            if (p.val < minPan) minPan = p.val;
            if (p.val > maxPan) maxPan = p.val;
        });
        currentPanKeyframes.forEach(kf => {
            if (kf.value < minPan) minPan = kf.value;
            if (kf.value > maxPan) maxPan = kf.value;
        });

        sampledTilt.forEach(p => {
            if (p.val < minTilt) minTilt = p.val;
            if (p.val > maxTilt) maxTilt = p.val;
        });
        currentTiltKeyframes.forEach(kf => {
            if (kf.value < minTilt) minTilt = kf.value;
            if (kf.value > maxTilt) maxTilt = kf.value;
        });

        let degMin = Math.min(minPan, minTilt, 0);
        let degMax = Math.max(maxPan, maxTilt, 10);
        let degSpan = Math.max(20, degMax - degMin);
        let padDeg = degSpan * 0.12;
        return {
            yMin: degMin - padDeg,
            yMax: degMax + padDeg,
            yRange: (degMax + padDeg) - (degMin - padDeg),
            padL: 55,
            padR: 25,
            padT: 25,
            padB: 40,
            plotW: 640 - 55 - 25,
            plotH: 250 - 25 - 40
        };
    };

    // Pointer Down (Start Drag / Select)
    svg.addEventListener("pointerdown", (e) => {
        const target = e.target.closest("[data-track]");
        if (!target) return;

        const track = target.getAttribute("data-track");
        const type = target.getAttribute("data-type") || track;
        const kidx = parseInt(target.getAttribute("data-kidx"), 10);
        const list = track === "pan" ? currentPanKeyframes : currentTiltKeyframes;
        if (isNaN(kidx) || kidx < 0 || kidx >= list.length) return;

        svg.setPointerCapture(e.pointerId);
        const svgCoords = getSvgCoords(e);

        curveDragState = {
            pointerId: e.pointerId,
            track: track, // 'pan' or 'tilt'
            type: type,   // 'pan', 'tilt', or 'time'
            kidx: kidx,
            startX: svgCoords.x,
            startY: svgCoords.y,
            origProgress: list[kidx].progress,
            origValue: list[kidx].value
        };

        selectKeyframe(track, kidx);
    });

    // Pointer Move (Live Drag & Tooltip)
    svg.addEventListener("pointermove", (e) => {
        const svgCoords = getSvgCoords(e);
        const b = getBounds();

        if (curveDragState && e.pointerId === curveDragState.pointerId) {
            const track = curveDragState.track;
            const list = track === "pan" ? currentPanKeyframes : currentTiltKeyframes;
            const kidx = curveDragState.kidx;
            const kf = list[kidx];
            const isStart = kidx === 0;
            const isEnd = kidx === list.length - 1;
            const isIntermediate = !isStart && !isEnd;

            // 1. Horizontal Progress Dragging (Time axis)
            if (isIntermediate) {
                const prevP = list[kidx - 1].progress;
                const nextP = list[kidx + 1].progress;
                const rawP = (svgCoords.x - b.padL) / b.plotW;
                kf.progress = Math.max(prevP + 0.015, Math.min(nextP - 0.015, Math.round(rawP * 1000) / 1000));
            }

            // 2. Vertical Value Dragging (Angle axis)
            if (curveDragState.type === "pan" || curveDragState.type === "tilt") {
                const rawDeg = b.yMin + ((b.padT + b.plotH - svgCoords.y) / b.plotH) * b.yRange;
                if (track === "pan") {
                    kf.value = Math.round(rawDeg * 2) / 2; // Snap to 0.5°
                } else {
                    kf.value = Math.max(0, Math.min(80, Math.round(rawDeg * 2) / 2)); // Clamped 0-80°
                }
            }

            // Fast preview redraw
            updateTrajectoryPreview();
            updateInspectorUI();

            // Floating Tooltip HUD
            if (tooltip) {
                const rect = svg.getBoundingClientRect();
                const totalShots = parseInt(document.getElementById("planTotalShots")?.value, 10) || 20;
                const shotNum = Math.max(1, Math.round(kf.progress * (totalShots - 1) + 1));
                const trackColor = track === "pan" ? "#38bdf8" : "#34d399";
                const trackName = track === "pan" ? "PAN" : "TILT";
                
                tooltip.style.display = "block";
                tooltip.style.left = `${e.clientX - rect.left}px`;
                tooltip.style.top = `${e.clientY - rect.top - 12}px`;
                tooltip.innerHTML = `
                    <div style="font-weight:bold; color:${trackColor};">${trackName} WAYPOINT #${kidx + 1} (${kf.outgoing_mode.toUpperCase()})</div>
                    <div>Time: <strong>${(kf.progress * 100).toFixed(0)}%</strong> (t = ${kf.progress.toFixed(2)}, Shot ${shotNum}/${totalShots})</div>
                    <div>Angle: <strong style="color:${trackColor};">${kf.value.toFixed(1)}°</strong></div>
                `;
            }
        } else {
            // Hover Tooltip on Nodes
            const target = e.target.closest("[data-track]");
            if (target && tooltip) {
                const track = target.getAttribute("data-track");
                const kidx = parseInt(target.getAttribute("data-kidx"), 10);
                const list = track === "pan" ? currentPanKeyframes : currentTiltKeyframes;
                const kf = list && list[kidx];
                if (kf) {
                    const rect = svg.getBoundingClientRect();
                    const totalShots = parseInt(document.getElementById("planTotalShots")?.value, 10) || 20;
                    const shotNum = Math.max(1, Math.round(kf.progress * (totalShots - 1) + 1));
                    const trackColor = track === "pan" ? "#38bdf8" : "#34d399";
                    const trackName = track === "pan" ? "PAN" : "TILT";
                    
                    tooltip.style.display = "block";
                    tooltip.style.left = `${e.clientX - rect.left}px`;
                    tooltip.style.top = `${e.clientY - rect.top - 12}px`;
                    tooltip.innerHTML = `
                        <div style="font-weight:bold; color:${trackColor};">${trackName} WAYPOINT #${kidx + 1}</div>
                        <div>Time: <strong>${(kf.progress * 100).toFixed(0)}%</strong> (t = ${kf.progress.toFixed(2)}, Shot ${shotNum})</div>
                        <div>Angle: <strong style="color:${trackColor};">${kf.value.toFixed(1)}°</strong></div>
                    `;
                }
            } else if (tooltip && !curveDragState) {
                tooltip.style.display = "none";
            }
        }
    });

    // Pointer Up (Finalize Drag)
    const endDrag = (e) => {
        if (curveDragState && e.pointerId === curveDragState.pointerId) {
            try { svg.releasePointerCapture(e.pointerId); } catch (err) {}
            curveDragState = null;
            renderKeyframeTable();
            updateTrajectoryPreview();
            if (tooltip) tooltip.style.display = "none";
        }
    };

    svg.addEventListener("pointerup", endDrag);
    svg.addEventListener("pointercancel", endDrag);
    svg.addEventListener("pointerleave", () => {
        if (!curveDragState && tooltip) tooltip.style.display = "none";
    });

    // Double-Click to Add Waypoint on Curve
    svg.addEventListener("dblclick", (e) => {
        const svgCoords = getSvgCoords(e);
        const b = getBounds();
        const rawP = (svgCoords.x - b.padL) / b.plotW;
        const clickT = Math.max(0.05, Math.min(0.95, Math.round(rawP * 100) / 100));

        let chosenTrack = "pan";
        if (curveFilter === "pan") {
            chosenTrack = "pan";
        } else if (curveFilter === "tilt") {
            chosenTrack = "tilt";
        } else {
            // Find which curve is closer to click Y
            const sampledPan = sampleTrackSpline(currentPanKeyframes, 100);
            const sampledTilt = sampleTrackSpline(currentTiltKeyframes, 100);
            const pIdx = Math.min(sampledPan.length - 1, Math.floor(clickT * (sampledPan.length - 1)));
            const tIdx = Math.min(sampledTilt.length - 1, Math.floor(clickT * (sampledTilt.length - 1)));
            const yPan = b.padT + b.plotH - ((sampledPan[pIdx].val - b.yMin) / b.yRange) * b.plotH;
            const yTilt = b.padT + b.plotH - ((sampledTilt[tIdx].val - b.yMin) / b.yRange) * b.plotH;

            chosenTrack = Math.abs(svgCoords.y - yPan) <= Math.abs(svgCoords.y - yTilt) ? "pan" : "tilt";
        }

        const list = chosenTrack === "pan" ? currentPanKeyframes : currentTiltKeyframes;
        const sampled = sampleTrackSpline(list, 100);
        let sampleVal = chosenTrack === "pan" ? latestPan : latestTilt;
        if (sampled.length > 0) {
            const sIdx = Math.min(sampled.length - 1, Math.floor(clickT * (sampled.length - 1)));
            sampleVal = sampled[sIdx].val;
        }

        const newKf = {
            progress: clickT,
            value: Math.round(sampleVal * 10) / 10,
            outgoing_mode: "smooth",
            tangent_scale: 1.0
        };

        list.push(newKf);
        list.sort((a, b) => a.progress - b.progress);
        selectedTrack = chosenTrack;
        selectedKeyframeIndex = list.indexOf(newKf);

        renderKeyframeTable();
        updateTrajectoryPreview();
    });
}

// --------------------------------------------------------------------------
// Dry Run Rehearsal Controls
// --------------------------------------------------------------------------

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
        dryRunProgressPct = 0;
        updateTrajectoryPreview();
    } catch (e) {}
}

function updateDryRunTelemetry(dr) {
    if (!dr) return;
    dryRunProgressPct = dr.progress_pct ?? 0;
    const pct = dryRunProgressPct.toFixed(0);
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
            dryRunActive = false;
        } else if (dr.state === "RUNNING") {
            badge.textContent = "Clearance: REHEARSING...";
            badge.className = "badge";
            dryRunActive = true;
        } else if (dr.state === "ERROR") {
            badge.textContent = "Clearance: ERROR";
            badge.className = "badge danger";
            dryRunActive = false;
        }
    }

    updateTrajectoryPreview();
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

// --------------------------------------------------------------------------
// Test Shot Verification Inspector & Pan/Zoom Viewport Controller
// --------------------------------------------------------------------------

let currentTestShotsList = [];
let activeTestShotIndex = 0;
let testShotZoom = 1.0;
let testShotPanX = 0;
let testShotPanY = 0;
let isPanningTestShot = false;
let panStartX = 0;
let panStartY = 0;
let testShotListenersInitialized = false;

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
    currentTestShotsList = shots || [];

    if (currentTestShotsList.length === 0) {
        gallery.innerHTML = `
            <div class="placeholder-box" style="grid-column:1/-1; padding: 24px; text-align: center;">
                <div style="font-size: 1.5rem; margin-bottom: 6px;">📷</div>
                <div style="font-weight: 500; color: #94a3b8;">No test shots taken yet</div>
                <div style="font-size: 0.75rem; color: #64748b; margin-top: 4px;">Click '⚡ Take Test Shot' to capture an exposure verification frame.</div>
            </div>
        `;
        return;
    }

    currentTestShotsList.forEach((s, idx) => {
        const item = document.createElement("div");
        item.className = "gallery-item";
        const sId = s.id || s.shot_id || s.artifact_id;
        const thumbUrl = `${API_BASE}/api/plans/${activePlan.id}/test-shots/${sId}/artifacts/preview.jpg`;
        const shutter = s.camera_settings?.shutter_speed || s.requested_settings?.shutter_speed || "1/125";
        const ap = s.camera_settings?.aperture || s.requested_settings?.aperture || "4.5";
        const iso = s.camera_settings?.iso || s.requested_settings?.iso || "400";
        const timeStr = s.created_at ? new Date(s.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : `#${idx + 1}`;

        item.innerHTML = `
            <div class="gallery-thumb-wrap">
                <img class="gallery-thumb" src="${thumbUrl}" alt="Test Shot #${idx + 1}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'160\\' height=\\'110\\'><rect fill=\\'%23020617\\' width=\\'160\\' height=\\'110\\'/><text fill=\\'%2364748b\\' x=\\'50%\\' y=\\'50%\\' dominant-baseline=\\'middle\\' text-anchor=\\'middle\\' font-family=\\'sans-serif\\' font-size=\\'12\\'>PREVIEW</text></svg>'">
                <div class="gallery-hover-overlay">
                    <span>🔍 Inspect Verification</span>
                </div>
            </div>
            <div class="gallery-info">
                <div class="gallery-title">${shutter}s · f/${ap}</div>
                <div class="gallery-sub">
                    <span>ISO ${iso}</span>
                    <span>${timeStr}</span>
                </div>
            </div>
        `;
        item.onclick = () => openTestShotInspector(idx);
        gallery.appendChild(item);
    });
}

function openTestShotInspector(index) {
    if (!currentTestShotsList || currentTestShotsList.length === 0) return;
    if (index < 0) index = 0;
    if (index >= currentTestShotsList.length) index = currentTestShotsList.length - 1;
    activeTestShotIndex = index;

    const shot = currentTestShotsList[activeTestShotIndex];
    if (!shot) return;
    const shotId = shot.id || shot.shot_id || shot.artifact_id;

    // Reset zoom and pan on open
    resetTestShotZoom();
    initTestShotViewportEvents();

    // 1. Counter & Nav Buttons
    const badge = document.getElementById("inspShotCounterBadge");
    if (badge) badge.textContent = `Shot ${activeTestShotIndex + 1} of ${currentTestShotsList.length}`;
    
    const prevBtn = document.getElementById("btnPrevTestShot");
    const nextBtn = document.getElementById("btnNextTestShot");
    if (prevBtn) prevBtn.disabled = activeTestShotIndex <= 0;
    if (nextBtn) nextBtn.disabled = activeTestShotIndex >= currentTestShotsList.length - 1;

    // 2. High-Res Image Source & Overlay
    const img = document.getElementById("testShotBigImage");
    const imgUrl = `${API_BASE}/api/plans/${activePlan.id}/test-shots/${shotId}/artifacts/preview.jpg`;
    if (img) {
        img.src = imgUrl;
        img.onload = () => {
            const dimEl = document.getElementById("lblTestShotDims");
            if (dimEl) dimEl.textContent = `${img.naturalWidth || 1920} × ${img.naturalHeight || 1080} px`;
        };
    }

    const origArtifact = (shot.artifacts || []).find(a => a.type === "original") || (shot.artifacts || [])[0];
    const sizeEl = document.getElementById("lblTestShotSize");
    if (sizeEl) {
        const bytes = origArtifact?.byte_size || 0;
        sizeEl.textContent = bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${(bytes / 1024).toFixed(0)} KB`;
    }

    // 3. Exposure Badges
    const shutter = shot.camera_settings?.shutter_speed || "1/125";
    const aperture = shot.camera_settings?.aperture || "4.5";
    const iso = shot.camera_settings?.iso || "400";
    const format = shot.camera_settings?.camera_format || "JPEG";

    document.getElementById("inspValShutter").textContent = shutter.endsWith("s") ? shutter : `${shutter}s`;
    document.getElementById("inspValAperture").textContent = aperture.startsWith("f/") ? aperture : `f/${aperture}`;
    document.getElementById("inspValIso").textContent = iso;
    document.getElementById("inspValFormat").textContent = format;

    // 4. Verification Diagnostics & Interval Clearance Check
    const planInterval = parseFloat(document.getElementById("planInterval")?.value) || 5.0;
    const planSettle = parseFloat(document.getElementById("planSettle")?.value) || 0.5;
    
    // Parse shutter duration in seconds
    let shutterSec = 0.008; // default ~ 1/125
    if (shutter.includes("/")) {
        const parts = shutter.split("/");
        shutterSec = (parseFloat(parts[0]) || 1) / (parseFloat(parts[1]) || 125);
    } else {
        shutterSec = parseFloat(shutter.replace("s", "")) || 1.0;
    }

    const totalShotBudget = shutterSec + planSettle;
    const vIconTiming = document.getElementById("vIconTiming");
    const vTextTiming = document.getElementById("vTextTiming");
    if (vIconTiming && vTextTiming) {
        if (totalShotBudget >= planInterval) {
            vIconTiming.textContent = "⚠️";
            vTextTiming.innerHTML = `<strong style="color:#f87171;">Timing Warning:</strong> Exposure (${shutterSec.toFixed(2)}s) + Settle (${planSettle.toFixed(1)}s) = ${totalShotBudget.toFixed(2)}s exceeds Interval (${planInterval.toFixed(1)}s). Increase interval or shorten shutter speed!`;
        } else {
            vIconTiming.textContent = "✅";
            vTextTiming.innerHTML = `<strong>Interval Clearance:</strong> Exposure (${shutterSec.toFixed(2)}s) + Settle (${planSettle.toFixed(1)}s) = ${totalShotBudget.toFixed(2)}s fits comfortably inside ${planInterval.toFixed(1)}s interval.`;
        }
    }

    const vIconExposure = document.getElementById("vIconExposure");
    const vTextExposure = document.getElementById("vTextExposure");
    if (vIconExposure && vTextExposure) {
        const isoNum = parseInt(iso, 10) || 400;
        if (isoNum >= 6400) {
            vIconExposure.textContent = "ℹ️";
            vTextExposure.innerHTML = `<strong style="color:#fbbf24;">High ISO Sensitivity:</strong> ISO ${isoNum} will enable dark scene capture but may introduce noise. Verify shadow sharpness.`;
        } else {
            vIconExposure.textContent = "✅";
            vTextExposure.innerHTML = `<strong>Exposure Check:</strong> Aperture f/${aperture} at ISO ${iso} offers crisp depth of field and low noise.`;
        }
    }

    // 5. Rig Angles at Exposure
    const panAngle = shot.rig_pose?.pan_deg ?? shot.extra_metadata?.rig_pan ?? latestPan ?? 0.0;
    const tiltAngle = shot.rig_pose?.tilt_deg ?? shot.extra_metadata?.rig_tilt ?? latestTilt ?? 0.0;
    document.getElementById("inspValPan").textContent = `${typeof panAngle === 'number' ? panAngle.toFixed(2) : panAngle}°`;
    document.getElementById("inspValTilt").textContent = `${typeof tiltAngle === 'number' ? tiltAngle.toFixed(2) : tiltAngle}°`;

    // 6. Capture Metadata Details
    const timeEl = document.getElementById("inspValTime");
    if (timeEl) timeEl.textContent = shot.created_at ? new Date(shot.created_at).toLocaleString() : "Just now";
    
    const shaEl = document.getElementById("inspValSha256");
    if (shaEl) {
        const sha = origArtifact?.checksum_sha256 || "--";
        shaEl.textContent = sha.length > 16 ? sha.substring(0, 16) + "..." : sha;
        shaEl.onclick = () => {
            navigator.clipboard.writeText(sha);
            alert("Copied SHA256 checksum to clipboard!");
        };
    }

    const planIdEl = document.getElementById("inspValPlanId");
    if (planIdEl) planIdEl.textContent = activePlan.id ? activePlan.id.substring(0, 12) + "..." : "--";

    // 7. Complete Raw JSON Drawer
    const jsonPre = document.getElementById("metaJsonDisplay");
    if (jsonPre) jsonPre.textContent = JSON.stringify(shot, null, 2);

    // Show modal
    document.getElementById("testShotInspectorModal")?.classList.remove("hidden");
}

function closeTestShotInspector() {
    document.getElementById("testShotInspectorModal")?.classList.add("hidden");
    const drawer = document.getElementById("rawMetaDrawer");
    if (drawer) drawer.classList.add("hidden");
}

function navigateTestShot(delta) {
    openTestShotInspector(activeTestShotIndex + delta);
}

function toggleRawMetadataDrawer() {
    const drawer = document.getElementById("rawMetaDrawer");
    if (drawer) drawer.classList.toggle("hidden");
}

// --------------------------------------------------------------------------
// Pan & Zoom Viewport Controls for Sharpness Inspection
// --------------------------------------------------------------------------

function initTestShotViewportEvents() {
    if (testShotListenersInitialized) return;
    testShotListenersInitialized = true;

    const viewport = document.getElementById("testShotViewport");
    if (!viewport) return;

    viewport.addEventListener("mousedown", (e) => {
        if (e.button !== 0) return; // Left click only
        isPanningTestShot = true;
        panStartX = e.clientX - testShotPanX;
        panStartY = e.clientY - testShotPanY;
        viewport.style.cursor = "grabbing";
    });

    window.addEventListener("mousemove", (e) => {
        if (!isPanningTestShot) return;
        testShotPanX = e.clientX - panStartX;
        testShotPanY = e.clientY - panStartY;
        updateTestShotTransform();
    });

    window.addEventListener("mouseup", () => {
        if (isPanningTestShot) {
            isPanningTestShot = false;
            const vp = document.getElementById("testShotViewport");
            if (vp) vp.style.cursor = "grab";
        }
    });

    viewport.addEventListener("wheel", (e) => {
        e.preventDefault();
        const delta = e.deltaY < 0 ? 0.2 : -0.2;
        adjustTestShotZoom(delta);
    }, { passive: false });

    // Global Key Listener for arrow navigation & Escape
    window.addEventListener("keydown", (e) => {
        const testModal = document.getElementById("testShotInspectorModal");
        if (testModal && !testModal.classList.contains("hidden")) {
            if (e.key === "ArrowLeft") navigateTestShot(-1);
            if (e.key === "ArrowRight") navigateTestShot(1);
            if (e.key === "Escape") closeTestShotInspector();
        }
        const liveModal = document.getElementById("enlargedLiveViewModal");
        if (liveModal && !liveModal.classList.contains("hidden")) {
            if (e.key === "Escape") closeEnlargedLiveViewModal();
        }
    });
}

function adjustTestShotZoom(delta) {
    testShotZoom = Math.max(0.5, Math.min(5.0, Math.round((testShotZoom + delta) * 100) / 100));
    updateTestShotTransform();
}

function resetTestShotZoom() {
    testShotZoom = 1.0;
    testShotPanX = 0;
    testShotPanY = 0;
    updateTestShotTransform();
}

function setTestShotActualPixels() {
    testShotZoom = 2.0; // 100% pixel zoom
    updateTestShotTransform();
}

function updateTestShotTransform() {
    const wrapper = document.getElementById("testShotImgWrapper");
    const lbl = document.getElementById("lblTestShotZoomLevel");
    if (wrapper) {
        wrapper.style.transform = `translate(${testShotPanX}px, ${testShotPanY}px) scale(${testShotZoom})`;
    }
    if (lbl) {
        lbl.textContent = testShotZoom === 1.0 ? "Fit (100%)" : `${Math.round(testShotZoom * 100)}%`;
    }
}

function openTestShotOriginalTab() {
    const shot = currentTestShotsList[activeTestShotIndex];
    if (!shot || !activePlan) return;
    const shotId = shot.id || shot.shot_id || shot.artifact_id;
    const origUrl = `${API_BASE}/api/plans/${activePlan.id}/test-shots/${shotId}/artifacts/original`;
    window.open(origUrl, "_blank");
}

function adoptCurrentTestShotSettings() {
    const shot = currentTestShotsList[activeTestShotIndex];
    if (!shot || !activePlan) return;

    const iso = shot.camera_settings?.iso || shot.requested_settings?.iso;
    const shutter = shot.camera_settings?.shutter_speed || shot.requested_settings?.shutter_speed;
    const ap = shot.camera_settings?.aperture || shot.requested_settings?.aperture;
    const fmt = shot.camera_settings?.camera_format || shot.requested_settings?.camera_format;

    if (iso && document.getElementById("acqIso")) document.getElementById("acqIso").value = iso;
    if (shutter && document.getElementById("acqShutter")) document.getElementById("acqShutter").value = shutter;
    if (ap && document.getElementById("acqAperture")) document.getElementById("acqAperture").value = ap;
    if (fmt && document.getElementById("acqFormat")) document.getElementById("acqFormat").value = fmt;

    saveCurrentPlan();
    alert(`✅ Adopted test shot settings:\n• ISO: ${iso || "auto"}\n• Shutter: ${shutter || "auto"}\n• Aperture: ${ap || "auto"}\n\nSaved to '${activePlan.name}'!`);
}

async function retakeTestShotFromInspector() {
    closeTestShotInspector();
    await triggerPlanTestShot();
}

async function deleteCurrentTestShot() {
    const shot = currentTestShotsList[activeTestShotIndex];
    if (!shot || !activePlan) return;
    if (!confirm("Are you sure you want to delete this test shot?")) return;

    const shotId = shot.id || shot.shot_id || shot.artifact_id;
    try {
        const res = await fetch(`${API_BASE}/api/plans/${activePlan.id}/test-shots/${shotId}`, { method: "DELETE" });
        if (res.ok) {
            await loadTestShotsList();
            if (currentTestShotsList.length === 0) {
                closeTestShotInspector();
            } else {
                openTestShotInspector(Math.min(activeTestShotIndex, currentTestShotsList.length - 1));
            }
        } else {
            const data = await res.json();
            alert(data.detail?.message || "Failed to delete test shot");
        }
    } catch (e) {
        console.error("Delete test shot error:", e);
    }
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
        const ok = currentPanKeyframes && currentPanKeyframes.length >= 2 && currentTiltKeyframes && currentTiltKeyframes.length >= 2;
        chkTraj.className = ok ? "passed" : "failed";
        chkTraj.innerHTML = ok
            ? '<span class="chk-icon">✅</span> Trajectory Verified (2+ Keyframes on Pan & Tilt)'
            : '<span class="chk-icon">❌</span> Trajectory Requires At Least 2 Keyframes per Track';
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

    const startPan = currentPanKeyframes[0]?.value || 0;
    const endPan = currentPanKeyframes[currentPanKeyframes.length - 1]?.value || 0;
    const startTilt = currentTiltKeyframes[0]?.value || 0;
    const endTilt = currentTiltKeyframes[currentTiltKeyframes.length - 1]?.value || 0;

    try {
        const res = await fetch(`${API_BASE}/api/timelapse/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                total_shots: total,
                interval_s: interval,
                pause_s: settle,
                pan_step: (endPan - startPan) / Math.max(1, total - 1),
                tilt_step: (endTilt - startTilt) / Math.max(1, total - 1),
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
    setupCurveEventListeners();
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
