/**
 * pantiltlapse - Single-Screen Timeline Studio
 * Independent Per-Parameter Tracks, Curve Graph Editor,
 * Focus Darkroom, and Zero-Pause Live In-Flight Ramping.
 */

// Photographic exposure step dictionaries & fallbacks
const DEFAULT_ISO_CHOICES = ["100", "125", "160", "200", "250", "320", "400", "500", "640", "800", "1000", "1250", "1600", "2000", "2500", "3200", "4000", "5000", "6400", "12800"];
const DEFAULT_SHUTTER_CHOICES = [
  "1/8000", "1/6400", "1/5000", "1/4000", "1/3200", "1/2500", "1/2000", "1/1600", "1/1250", "1/1000", "1/800", "1/640", "1/500", "1/400", "1/320",
  "1/250", "1/200", "1/160", "1/125", "1/100", "1/80", "1/60", "1/50", "1/40", "1/30", "1/25", "1/20", "1/15", "1/13", "1/10",
  "1/8", "1/6", "1/5", "1/4", "0.3", "0.4", "0.5", "0.6", "0.8", "1", "1.3", "1.6", "2", "2.5", "3.2", "4", "5", "6", "8", "10", "13", "15", "20", "25", "30"
];
const DEFAULT_APERTURE_CHOICES = ["1.4", "1.8", "2.0", "2.2", "2.5", "2.8", "3.2", "3.5", "4.0", "4.5", "5.0", "5.6", "6.3", "7.1", "8.0", "9.0", "10", "11", "13", "14", "16", "18", "20", "22"];
const DEFAULT_WB_CHOICES = ["Auto", "Daylight", "Cloudy", "Shade", "Tungsten", "Fluorescent", "Flash", "Custom"];

class TimelineStudioApp {
  constructor() {
    this.plan = {
      name: "Sunset Sequence",
      totalShots: 240,
      interval_s: 5.0,
      settle_time_s: 0.5,
      defaults: {
        iso: "100",
        shutter_speed: "1/250",
        aperture: "4.0",
        white_balance: "Auto"
      },
      tracks: {
        pan: {
          id: "pan",
          label: "Pan Axis",
          color: "#06b6d4",
          unit: "deg",
          type: "continuous",
          keyframes: [
            { id: "p1", shotIndex: 1, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] },
            { id: "p2", shotIndex: 240, value: 30.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] }
          ]
        },
        tilt: {
          id: "tilt",
          label: "Tilt Axis",
          color: "#f97316",
          unit: "deg",
          type: "continuous",
          keyframes: [
            { id: "t1", shotIndex: 1, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] },
            { id: "t2", shotIndex: 240, value: 12.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] }
          ]
        }
      }
    };

    this.playhead = 1; // 1-based trigger index
    this.activeTrackId = "pan";
    this.selectedKeyId = "p1";
    this.zoom = 1.0;
    this.scrollX = 0;
    this.viewMode = "tracks"; // 'tracks' or 'curve'

    // Virtual Preview Playback
    this.isPlayingPreview = false;
    this.previewIntervalId = null;

    // Viewport & Loupe State
    this.isLiveViewActive = false;
    this.isLoupeActive = false;

    // Camera Choices
    this.cameraChoices = {
      iso: [...DEFAULT_ISO_CHOICES],
      shutter_speed: [...DEFAULT_SHUTTER_CHOICES],
      aperture: [...DEFAULT_APERTURE_CHOICES],
      white_balance: [...DEFAULT_WB_CHOICES]
    };

    // Hardware SSE state
    this.liveState = {
      motors: { pan: 0.0, tilt: 0.0, is_connected: false, state: "DISCONNECTED" },
      camera: { is_connected: false, model: "Unknown", iso: "100", shutter_speed: "1/250", aperture: "4.0", white_balance: "Auto" },
      rig: { reference_confirmed: false, zero_state: "UNCONFIRMED" },
      timelapse: { state: "IDLE", current_shot: 0, total_shots: 0 }
    };

    // Mouse Interaction
    this.dragTarget = null;
    this.isDragging = false;
    this.pendingOffsetChange = null;

    this.initDOM();
    this.bindEvents();
    this.initCanvas();
    this.fetchCameraChoices();
    this.initSSE();
    this.updateScheduleCalculations();
    this.checkShutterIntervalSafety();
    this.renderTrackHeaders();
    this.updateInspectorUI();
    this.renderTimeline();
  }

  /* -------------------------------------------------------------------------- */
  /* DOM & Elements Setup                                                      */
  /* -------------------------------------------------------------------------- */
  initDOM() {
    this.dom = {
      planNameInput: document.getElementById("planNameInput"),
      btnSavePlan: document.getElementById("btnSavePlan"),
      zeroRefBadge: document.getElementById("zeroRefBadge"),
      zeroRefText: document.getElementById("zeroRefText"),
      motorBadge: document.getElementById("motorBadge"),
      motorText: document.getElementById("motorText"),
      cameraBadge: document.getElementById("cameraBadge"),
      cameraText: document.getElementById("cameraText"),
      modeBadge: document.getElementById("modeBadge"),
      modeText: document.getElementById("modeText"),
      btnConfirmZero: document.getElementById("btnConfirmZero"),
      btnStartTimelapse: document.getElementById("btnStartTimelapse"),
      btnPauseTimelapse: document.getElementById("btnPauseTimelapse"),
      btnStop: document.getElementById("btnStop"),

      // Banners
      execZeroWarningBanner: document.getElementById("execZeroWarningBanner"),
      intervalWarningBanner: document.getElementById("intervalWarningBanner"),
      intervalWarningText: document.getElementById("intervalWarningText"),
      btnAutoAdjustInterval: document.getElementById("btnAutoAdjustInterval"),

      // Viewport & Loupe
      viewportContainer: document.getElementById("viewportContainer"),
      previewImage: document.getElementById("previewImage"),
      loupeOverlay: document.getElementById("loupeOverlay"),
      viewportPlaceholder: document.getElementById("viewportPlaceholder"),
      shotCounterOverlay: document.getElementById("shotCounterOverlay"),
      timingOverlay: document.getElementById("timingOverlay"),
      interpolatedPoseOverlay: document.getElementById("interpolatedPoseOverlay"),
      btnToggleLiveView: document.getElementById("btnToggleLiveView"),
      btnTakeSnapshot: document.getElementById("btnTakeSnapshot"),
      btnMoveToPlayheadPose: document.getElementById("btnMoveToPlayheadPose"),
      liveRigFeedback: document.getElementById("liveRigFeedback"),
      btnRestartCam: document.getElementById("btnRestartCam"),

      // Focus Station
      btnAutoFocus: document.getElementById("btnAutoFocus"),
      btnFocusFar3: document.getElementById("btnFocusFar3"),
      btnFocusFar1: document.getElementById("btnFocusFar1"),
      btnFocusNear1: document.getElementById("btnFocusNear1"),
      btnFocusNear3: document.getElementById("btnFocusNear3"),
      btnToggleLoupe: document.getElementById("btnToggleLoupe"),
      btnStarSnap: document.getElementById("btnStarSnap"),

      // Schedule inputs
      totalShotsInput: document.getElementById("totalShotsInput"),
      intervalInput: document.getElementById("intervalInput"),
      settleInput: document.getElementById("settleInput"),
      calcRunTime: document.getElementById("calcRunTime"),
      calcClipLength: document.getElementById("calcClipLength"),

      // Key Trigger Inspector
      inspectorTrackTitle: document.getElementById("inspectorTrackTitle"),
      keyTriggerCard: document.getElementById("keyTriggerCard"),
      keyCardTitle: document.getElementById("keyCardTitle"),
      btnToggleKeyTrigger: document.getElementById("btnToggleKeyTrigger"),
      lblParameterValue: document.getElementById("lblParameterValue"),
      numericValueGroup: document.getElementById("numericValueGroup"),
      keyNumericInput: document.getElementById("keyNumericInput"),
      numericInputUnit: document.getElementById("numericInputUnit"),
      discreteValueGroup: document.getElementById("discreteValueGroup"),
      keyDiscreteSelect: document.getElementById("keyDiscreteSelect"),
      easingContainer: document.getElementById("easingContainer"),
      keyEasingSelect: document.getElementById("keyEasingSelect"),

      // Defaults
      btnSyncFromCam: document.getElementById("btnSyncFromCam"),
      defaultIsoSelect: document.getElementById("defaultIsoSelect"),
      defaultShutterSelect: document.getElementById("defaultShutterSelect"),
      defaultApertureSelect: document.getElementById("defaultApertureSelect"),
      defaultWbSelect: document.getElementById("defaultWbSelect"),

      // Timeline Toolbar
      btnFirstShot: document.getElementById("btnFirstShot"),
      btnPrevKey: document.getElementById("btnPrevKey"),
      btnPlayPreview: document.getElementById("btnPlayPreview"),
      btnNextKey: document.getElementById("btnNextKey"),
      btnLastShot: document.getElementById("btnLastShot"),
      playheadInput: document.getElementById("playheadInput"),
      totalShotsLabel: document.getElementById("totalShotsLabel"),
      btnAddKeyTrigger: document.getElementById("btnAddKeyTrigger"),
      zoomSlider: document.getElementById("zoomSlider"),
      btnToggleCurveGraph: document.getElementById("btnToggleCurveGraph"),

      // Timeline Headers & Canvas
      timelineHeaders: document.getElementById("timelineHeaders"),
      canvasContainer: document.getElementById("timelineCanvasContainer"),
      canvas: document.getElementById("timelineCanvas"),
      toastContainer: document.getElementById("toastContainer"),

      // Modals
      offsetChoiceModal: document.getElementById("offsetChoiceModal"),
      offsetPromptText: document.getElementById("offsetPromptText"),
      btnOffsetHoldOnly: document.getElementById("btnOffsetHoldOnly"),
      btnOffsetShiftAll: document.getElementById("btnOffsetShiftAll")
    };
  }

  /* -------------------------------------------------------------------------- */
  /* Event Listeners                                                            */
  /* -------------------------------------------------------------------------- */
  bindEvents() {
    // Schedule inputs
    this.dom.totalShotsInput.addEventListener("change", (e) => {
      this.setTotalShots(Math.max(2, parseInt(e.target.value) || 2));
    });
    this.dom.intervalInput.addEventListener("change", (e) => {
      this.plan.interval_s = Math.max(1.0, parseFloat(e.target.value) || 5.0);
      this.updateScheduleCalculations();
      this.checkShutterIntervalSafety();
    });
    this.dom.settleInput.addEventListener("change", (e) => {
      this.plan.settle_time_s = Math.max(0.0, parseFloat(e.target.value) || 0.5);
      this.checkShutterIntervalSafety();
    });
    this.dom.btnAutoAdjustInterval.addEventListener("click", () => this.autoAdjustInterval());

    // Sequence Camera Defaults
    const updateDefault = (param, val) => {
      this.plan.defaults[param] = val;
      this.cleanupCameraTrack(param);
      this.checkShutterIntervalSafety();
      this.updateOverlays();
      this.renderTimeline();
      this.checkLiveRamping(param, val);
    };
    this.dom.defaultIsoSelect.addEventListener("change", (e) => updateDefault("iso", e.target.value));
    this.dom.defaultShutterSelect.addEventListener("change", (e) => updateDefault("shutter_speed", e.target.value));
    this.dom.defaultApertureSelect.addEventListener("change", (e) => updateDefault("aperture", e.target.value));
    this.dom.defaultWbSelect.addEventListener("change", (e) => updateDefault("white_balance", e.target.value));
    this.dom.btnSyncFromCam.addEventListener("click", () => this.syncFromCameraSettings());

    // Key Trigger Value Input Events
    this.dom.keyNumericInput.addEventListener("input", (e) => {
      const track = this.plan.tracks[this.activeTrackId];
      if (!track || track.type !== "continuous") return;
      let key = this.getKeyTriggerAtShot(track, this.playhead);
      if (!key) {
        this.addKeyTriggerAtPlayhead();
        key = this.getKeyTriggerAtShot(track, this.playhead);
      }
      if (key) {
        key.value = parseFloat(e.target.value) || 0.0;
        this.renderTimeline();
        this.updateOverlays();
        this.checkLiveRamping(this.activeTrackId, key.value);
      }
    });

    this.dom.keyDiscreteSelect.addEventListener("change", (e) => {
      const paramKey = this.activeTrackId;
      const val = e.target.value;
      this.ensureCameraTrack(paramKey, val);
      this.renderTrackHeaders();
      this.updateInspectorUI();
      this.renderTimeline();
      this.updateOverlays();
      this.checkShutterIntervalSafety();
      this.checkLiveRamping(paramKey, val);
    });

    this.dom.keyEasingSelect.addEventListener("change", (e) => {
      const track = this.plan.tracks[this.activeTrackId];
      if (track && track.type === "continuous") {
        const key = this.getKeyTriggerAtShot(track, this.playhead);
        if (key) {
          key.mode = e.target.value;
          this.renderTimeline();
        }
      }
    });

    // Key Management
    this.dom.btnToggleKeyTrigger.addEventListener("click", () => this.toggleKeyTriggerAtPlayhead());
    this.dom.btnAddKeyTrigger.addEventListener("click", () => this.addKeyTriggerAtPlayhead());

    // Transport buttons
    this.dom.btnFirstShot.addEventListener("click", () => this.setPlayhead(1));
    this.dom.btnLastShot.addEventListener("click", () => this.setPlayhead(this.plan.totalShots));
    this.dom.btnPrevKey.addEventListener("click", () => this.goToPrevKey());
    this.dom.btnNextKey.addEventListener("click", () => this.goToNextKey());
    this.dom.btnPlayPreview.addEventListener("click", () => this.togglePreviewPlayback());

    this.dom.playheadInput.addEventListener("change", (e) => {
      this.setPlayhead(parseInt(e.target.value) || 1);
    });

    this.dom.zoomSlider.addEventListener("input", (e) => {
      this.zoom = parseFloat(e.target.value);
      this.renderTimeline();
    });

    // Mode Toggle (Track Bars vs 2D Curve Editor)
    this.dom.btnToggleCurveGraph.addEventListener("click", () => {
      this.viewMode = this.viewMode === "tracks" ? "curve" : "tracks";
      this.dom.btnToggleCurveGraph.classList.toggle("btn-primary", this.viewMode === "curve");
      this.dom.btnToggleCurveGraph.textContent = this.viewMode === "curve" ? "📊 Track View" : "📈 Curve Editor";
      this.renderTimeline();
    });

    // Viewport Actions
    this.dom.btnToggleLiveView.addEventListener("click", () => this.toggleLiveView());
    this.dom.btnTakeSnapshot.addEventListener("click", () => this.takeSnapshot());
    this.dom.btnMoveToPlayheadPose.addEventListener("click", () => this.commandRigToPlayheadPose());
    this.dom.btnRestartCam.addEventListener("click", () => this.restartCamera());

    // Focus Station Actions
    this.dom.btnAutoFocus.addEventListener("click", () => this.triggerAutoFocus());
    this.dom.btnFocusFar3.addEventListener("click", () => this.stepFocus("far", 3));
    this.dom.btnFocusFar1.addEventListener("click", () => this.stepFocus("far", 1));
    this.dom.btnFocusNear1.addEventListener("click", () => this.stepFocus("near", 1));
    this.dom.btnFocusNear3.addEventListener("click", () => this.stepFocus("near", 3));
    this.dom.btnToggleLoupe.addEventListener("click", () => this.toggleLoupe());
    this.dom.btnStarSnap.addEventListener("click", () => this.takeStarSnap());

    // Execution Controls
    this.dom.btnStartTimelapse.addEventListener("click", () => this.startTimelapse());
    this.dom.btnPauseTimelapse.addEventListener("click", () => this.pauseOrResumeTimelapse());
    this.dom.btnStop.addEventListener("click", () => this.emergencyStop());
    this.dom.btnSavePlan.addEventListener("click", () => this.savePlan());

    // Loupe Cursor Tracker on Viewport
    this.dom.viewportContainer.addEventListener("mousemove", (e) => this.onViewportMouseMove(e));
    this.dom.viewportContainer.addEventListener("mouseleave", () => {
      if (this.dom.loupeOverlay) this.dom.loupeOverlay.style.display = "none";
    });

    // In-Flight Offset Modal choices
    this.dom.btnOffsetHoldOnly.addEventListener("click", () => this.applyOffsetChoice("hold"));
    this.dom.btnOffsetShiftAll.addEventListener("click", () => this.applyOffsetChoice("shift_all"));

    // Keyboard Shortcuts
    window.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;

      if (e.code === "Space") {
        e.preventDefault();
        this.togglePreviewPlayback();
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        if (e.shiftKey) this.goToPrevKey();
        else this.setPlayhead(this.playhead - 1);
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        if (e.shiftKey) this.goToNextKey();
        else this.setPlayhead(this.playhead + 1);
      } else if (e.key === "k" || e.key === "K") {
        e.preventDefault();
        this.addKeyTriggerAtPlayhead();
      } else if (e.key === "Delete" || e.key === "Backspace") {
        const track = this.plan.tracks[this.activeTrackId];
        if (track) {
          const key = this.getKeyTriggerAtShot(track, this.playhead);
          if (key && (track.type !== "continuous" || track.keyframes.length > 2)) {
            e.preventDefault();
            this.deleteKeyTrigger(track.id, key.id);
          }
        }
      }
    });

    window.addEventListener("resize", () => {
      this.resizeCanvas();
      this.renderTimeline();
    });
  }

  /* -------------------------------------------------------------------------- */
  /* Camera Choices & Selects Setup                                             */
  /* -------------------------------------------------------------------------- */
  async fetchCameraChoices() {
    try {
      const res = await fetch("/api/camera/config/choices");
      if (res.ok) {
        const data = await res.json();
        if (data.choices) {
          if (data.choices.iso?.length) this.cameraChoices.iso = data.choices.iso;
          if (data.choices.shutter_speed?.length) this.cameraChoices.shutter_speed = data.choices.shutter_speed;
          if (data.choices.aperture?.length) this.cameraChoices.aperture = data.choices.aperture;
          if (data.choices.white_balance?.length) this.cameraChoices.white_balance = data.choices.white_balance;
        }
      }
    } catch (e) {
      console.warn("Could not fetch camera choices, using defaults:", e);
    }
    this.populateSelectOptions();
    this.updateInspectorUI();
  }

  populateSelectOptions() {
    const fill = (selectElem, items, defaultVal) => {
      selectElem.innerHTML = "";
      items.forEach((item) => {
        const opt = document.createElement("option");
        opt.value = item;
        opt.textContent = item;
        selectElem.appendChild(opt);
      });
      selectElem.value = defaultVal || items[0];
    };

    fill(this.dom.defaultIsoSelect, this.cameraChoices.iso, this.plan.defaults.iso);
    fill(this.dom.defaultShutterSelect, this.cameraChoices.shutter_speed, this.plan.defaults.shutter_speed);
    fill(this.dom.defaultApertureSelect, this.cameraChoices.aperture, this.plan.defaults.aperture);
    fill(this.dom.defaultWbSelect, this.cameraChoices.white_balance, this.plan.defaults.white_balance);
  }

  /* -------------------------------------------------------------------------- */
  /* Real-Time SSE Stream Integration                                          */
  /* -------------------------------------------------------------------------- */
  initSSE() {
    try {
      const es = new EventSource("/api/events");
      es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          this.handleLiveEvent(data);
        } catch (err) {
          console.error("SSE parse error", err);
        }
      };
      es.onerror = () => {
        this.dom.motorBadge.className = "status-badge error";
        this.dom.motorText.textContent = "DISCONNECTED";
      };
    } catch (e) {
      console.warn("SSE not available", e);
    }
  }

  handleLiveEvent(data) {
    if (data.motors) {
      this.liveState.motors = data.motors;
      const isConn = data.motors.is_connected;
      this.dom.motorBadge.className = `status-badge ${isConn ? "connected" : "error"}`;
      this.dom.motorText.textContent = isConn ? `MOTORS: ${data.motors.state || "ONLINE"}` : "MOTORS: OFF";
      this.dom.liveRigFeedback.textContent = `Rig: (${Number(data.motors.pan || 0).toFixed(1)}°, ${Number(data.motors.tilt || 0).toFixed(1)}°)`;
    }

    if (data.camera) {
      this.liveState.camera = data.camera;
      const isCam = data.camera.is_connected;
      this.dom.cameraBadge.className = `status-badge ${isCam ? "connected" : "error"}`;
      this.dom.cameraText.textContent = isCam ? `CAM: ${data.camera.model || "ONLINE"}` : "CAM: OFF";
    }

    if (data.reference) {
      const isZero = data.reference.reference_confirmed;
      this.dom.zeroRefBadge.className = `status-badge ${isZero ? "connected" : "warning"}`;
      this.dom.zeroRefText.textContent = isZero ? "ZERO: OK (0°, 0°)" : "ZERO: UNCONFIRMED";
      if (this.dom.execZeroWarningBanner) {
        this.dom.execZeroWarningBanner.style.display = isZero ? "none" : "flex";
      }
    }

    if (data.timelapse) {
      this.liveState.timelapse = data.timelapse;
      const tState = data.timelapse.state;
      this.dom.modeText.textContent = tState;
      if (tState === "RUNNING") {
        this.dom.btnStartTimelapse.style.display = "none";
        this.dom.btnPauseTimelapse.style.display = "inline-flex";
        this.dom.btnPauseTimelapse.textContent = "⏸ Pause";
        if (data.timelapse.current_shot > 0) {
          this.setPlayhead(data.timelapse.current_shot, false);
        }
      } else if (tState === "PAUSED") {
        this.dom.btnStartTimelapse.style.display = "none";
        this.dom.btnPauseTimelapse.style.display = "inline-flex";
        this.dom.btnPauseTimelapse.textContent = "▶ Resume";
      } else {
        this.dom.btnStartTimelapse.style.display = "inline-flex";
        this.dom.btnPauseTimelapse.style.display = "none";
      }
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Timeline Canvas Engine & Interaction                                       */
  /* -------------------------------------------------------------------------- */
  initCanvas() {
    this.canvas = this.dom.canvas;
    this.ctx = this.canvas.getContext("2d");
    this.resizeCanvas();

    this.canvas.addEventListener("mousedown", (e) => this.onCanvasMouseDown(e));
    window.addEventListener("mousemove", (e) => this.onCanvasMouseMove(e));
    window.addEventListener("mouseup", (e) => this.onCanvasMouseUp(e));

    this.canvas.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (e.ctrlKey || e.metaKey) {
        const delta = e.deltaY < 0 ? 0.25 : -0.25;
        this.zoom = Math.max(1.0, Math.min(10.0, this.zoom + delta));
        this.dom.zoomSlider.value = this.zoom;
      } else {
        this.scrollX = Math.max(0, this.scrollX + e.deltaX + e.deltaY * 0.5);
      }
      this.renderTimeline();
    }, { passive: false });
  }

  resizeCanvas() {
    const rect = this.dom.canvasContainer.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvasWidth = rect.width;
    this.canvasHeight = rect.height;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.resetTransform();
    this.ctx.scale(dpr, dpr);
  }

  shotToX(shotIndex) {
    const total = this.plan.totalShots;
    const padding = 20;
    const availableWidth = (this.canvasWidth - padding * 2) * this.zoom;
    const ratio = (shotIndex - 1) / (total - 1);
    return padding + ratio * availableWidth - this.scrollX;
  }

  xToShot(x) {
    const total = this.plan.totalShots;
    const padding = 20;
    const availableWidth = (this.canvasWidth - padding * 2) * this.zoom;
    const adjustedX = x + this.scrollX - padding;
    const ratio = Math.max(0.0, Math.min(1.0, adjustedX / availableWidth));
    return Math.round(1 + ratio * (total - 1));
  }

  renderTimeline() {
    if (!this.ctx) return;
    const w = this.canvasWidth;
    const h = this.canvasHeight;
    const ctx = this.ctx;

    ctx.clearRect(0, 0, w, h);

    const rulerH = 28;

    // Draw Top Ruler
    ctx.fillStyle = "#17191e";
    ctx.fillRect(0, 0, w, rulerH);
    this.renderRuler(ctx, rulerH);

    if (this.viewMode === "tracks") {
      this.renderTracksView(ctx, rulerH, w, h);
    } else {
      this.renderCurveEditorView(ctx, rulerH, w, h);
    }

    // Draw Playhead
    const phX = this.shotToX(this.playhead);
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(phX, 0);
    ctx.lineTo(phX, h);
    ctx.stroke();

    // Playhead handle on ruler
    ctx.fillStyle = "#ef4444";
    ctx.beginPath();
    ctx.moveTo(phX - 6, 0);
    ctx.lineTo(phX + 6, 0);
    ctx.lineTo(phX + 6, rulerH - 8);
    ctx.lineTo(phX, rulerH);
    ctx.lineTo(phX - 6, rulerH - 8);
    ctx.closePath();
    ctx.fill();
  }

  renderRuler(ctx, rulerH) {
    const total = this.plan.totalShots;
    ctx.fillStyle = "#64748b";
    ctx.font = "10px JetBrains Mono";
    ctx.textAlign = "center";

    let step = 10;
    if (this.zoom > 3) step = 2;
    else if (this.zoom > 1.5) step = 5;
    else if (total > 500) step = 50;

    for (let s = 1; s <= total; s += step) {
      const x = this.shotToX(s);
      if (x < -20 || x > this.canvasWidth + 20) continue;

      ctx.strokeStyle = "rgba(255, 255, 255, 0.2)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x + 0.5, rulerH - 8);
      ctx.lineTo(x + 0.5, rulerH);
      ctx.stroke();

      ctx.fillText(`${s}`, x, rulerH - 12);
    }
  }

  renderTracksView(ctx, rulerH, w, h) {
    const trackKeys = Object.keys(this.plan.tracks);
    const rowH = 44;

    trackKeys.forEach((trackId, idx) => {
      const track = this.plan.tracks[trackId];
      const y = rulerH + idx * rowH;

      // Row background
      ctx.fillStyle = idx % 2 === 0 ? "#121417" : "#14161b";
      ctx.fillRect(0, y, w, rowH);

      // Separator line
      ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
      ctx.beginPath();
      ctx.moveTo(0, y + rowH + 0.5);
      ctx.lineTo(w, y + rowH + 0.5);
      ctx.stroke();

      if (track.type === "continuous") {
        // Continuous line through keyframes
        ctx.strokeStyle = track.color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let s = 1; s <= this.plan.totalShots; s++) {
          const sx = this.shotToX(s);
          const val = this.evaluateTrackAtShot(track, s);
          // Normalize locally for row height
          const sy = y + rowH / 2 - Math.sin(s * 0.05) * 4; // visual subtle accent
          if (s === 1) ctx.moveTo(sx, sy);
          else ctx.lineTo(sx, sy);
        }
        ctx.stroke();

        // Keyframe Diamonds
        track.keyframes.forEach((key) => {
          const kx = this.shotToX(key.shotIndex);
          const isSelected = this.activeTrackId === track.id && this.selectedKeyId === key.id;
          this.drawDiamond(ctx, kx, y + rowH / 2, isSelected ? 8 : 6, isSelected ? "#facc15" : track.color);
        });
      } else {
        // Discrete stepped blocks
        const total = this.plan.totalShots;
        const sortedKeys = [...track.keyframes].sort((a, b) => a.shotIndex - b.shotIndex);

        for (let i = 0; i < sortedKeys.length; i++) {
          const kCurr = sortedKeys[i];
          const kNext = sortedKeys[i + 1];
          const startShot = kCurr.shotIndex;
          const endShot = kNext ? kNext.shotIndex : total;

          const startX = this.shotToX(startShot);
          const endX = this.shotToX(endShot);

          // Stepped block
          ctx.fillStyle = `${track.color}22`;
          ctx.fillRect(startX, y + 6, endX - startX, rowH - 12);
          ctx.strokeStyle = track.color;
          ctx.strokeRect(startX, y + 6, endX - startX, rowH - 12);

          // Value label
          ctx.fillStyle = "#fff";
          ctx.font = "10px JetBrains Mono";
          ctx.textAlign = "left";
          ctx.fillText(kCurr.value, startX + 6, y + rowH / 2 + 3);

          // Diamond at step point
          const isSelected = this.activeTrackId === track.id && this.selectedKeyId === kCurr.id;
          this.drawDiamond(ctx, startX, y + rowH / 2, isSelected ? 7 : 5, isSelected ? "#facc15" : track.color);
        }
      }
    });
  }

  renderCurveEditorView(ctx, rulerH, w, h) {
    const track = this.plan.tracks[this.activeTrackId];
    if (!track) return;

    const graphY = rulerH;
    const graphH = h - rulerH;

    // Graph Background
    ctx.fillStyle = "#111317";
    ctx.fillRect(0, graphY, w, graphH);

    // Compute range for vertical scale
    let minVal = -10;
    let maxVal = 40;
    if (track.keyframes.length > 0) {
      minVal = Math.min(...track.keyframes.map((k) => k.value));
      maxVal = Math.max(...track.keyframes.map((k) => k.value));
    }
    const padding = Math.max(5, (maxVal - minVal) * 0.2);
    minVal -= padding;
    maxVal += padding;
    const valRange = maxVal - minVal || 1;

    const valToY = (val) => graphY + graphH - 20 - ((val - minVal) / valRange) * (graphH - 40);

    // Horizontal Grid Lines
    ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
    ctx.fillStyle = "#475569";
    ctx.font = "10px JetBrains Mono";
    ctx.textAlign = "left";

    const gridStep = (maxVal - minVal) / 4;
    for (let i = 0; i <= 4; i++) {
      const gv = minVal + i * gridStep;
      const gy = valToY(gv);
      ctx.beginPath();
      ctx.moveTo(0, gy);
      ctx.lineTo(w, gy);
      ctx.stroke();
      ctx.fillText(`${gv.toFixed(1)}°`, 10, gy - 3);
    }

    // Render continuous Bezier curve
    ctx.strokeStyle = track.color;
    ctx.lineWidth = 2.5;
    ctx.beginPath();

    for (let s = 1; s <= this.plan.totalShots; s++) {
      const x = this.shotToX(s);
      const val = this.evaluateTrackAtShot(track, s);
      const y = valToY(val);

      if (s === 1) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Render Keypoints & Tangent Handles
    track.keyframes.forEach((key) => {
      const kx = this.shotToX(key.shotIndex);
      const ky = valToY(key.value);
      const isSelected = this.selectedKeyId === key.id;

      // Tangent handles for selected key
      if (isSelected && (key.mode === "bezier" || key.mode === "auto")) {
        const inX = kx + (key.inTangent?.[0] || -20);
        const inY = ky + (key.inTangent?.[1] || 0);
        const outX = kx + (key.outTangent?.[0] || 20);
        const outY = ky + (key.outTangent?.[1] || 0);

        ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
        ctx.lineWidth = 1.5;
        // In handle
        ctx.beginPath();
        ctx.moveTo(kx, ky);
        ctx.lineTo(inX, inY);
        ctx.stroke();
        ctx.fillStyle = "#38bdf8";
        ctx.beginPath();
        ctx.arc(inX, inY, 4, 0, Math.PI * 2);
        ctx.fill();

        // Out handle
        ctx.beginPath();
        ctx.moveTo(kx, ky);
        ctx.lineTo(outX, outY);
        ctx.stroke();
        ctx.fillStyle = "#38bdf8";
        ctx.beginPath();
        ctx.arc(outX, outY, 4, 0, Math.PI * 2);
        ctx.fill();
      }

      this.drawDiamond(ctx, kx, ky, isSelected ? 8 : 6, isSelected ? "#facc15" : track.color);
    });
  }

  drawDiamond(ctx, x, y, size, fill) {
    ctx.fillStyle = fill;
    ctx.beginPath();
    ctx.moveTo(x, y - size);
    ctx.lineTo(x + size, y);
    ctx.lineTo(x, y + size);
    ctx.lineTo(x - size, y);
    ctx.closePath();
    ctx.fill();
  }

  /* -------------------------------------------------------------------------- */
  /* Canvas Mouse Interactions                                                  */
  /* -------------------------------------------------------------------------- */
  onCanvasMouseDown(e) {
    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const track = this.plan.tracks[this.activeTrackId];

    // Check click on keypoints
    if (track) {
      for (const key of track.keyframes) {
        const kx = this.shotToX(key.shotIndex);
        if (Math.abs(mouseX - kx) < 12) {
          this.selectedKeyId = key.id;
          this.setPlayhead(key.shotIndex);
          this.dragTarget = { type: "key", trackId: track.id, id: key.id };
          this.isDragging = true;
          this.updateInspectorUI();
          this.renderTimeline();
          return;
        }
      }
    }

    // Otherwise scrub playhead
    const targetShot = this.xToShot(mouseX);
    this.setPlayhead(targetShot);
    this.dragTarget = { type: "playhead" };
    this.isDragging = true;
  }

  onCanvasMouseMove(e) {
    if (!this.isDragging || !this.dragTarget) return;

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const targetShot = this.xToShot(mouseX);

    if (this.dragTarget.type === "playhead") {
      this.setPlayhead(targetShot);
    } else if (this.dragTarget.type === "key") {
      const track = this.plan.tracks[this.dragTarget.trackId];
      if (track) {
        const key = track.keyframes.find((k) => k.id === this.dragTarget.id);
        if (key) {
          key.shotIndex = Math.max(1, Math.min(this.plan.totalShots, targetShot));
          track.keyframes.sort((a, b) => a.shotIndex - b.shotIndex);
          this.setPlayhead(key.shotIndex);
          this.updateInspectorUI();
          this.renderTimeline();
          this.checkLiveRamping(track.id, key.value);
        }
      }
    }
  }

  onCanvasMouseUp() {
    this.isDragging = false;
    this.dragTarget = null;
  }

  /* -------------------------------------------------------------------------- */
  /* Track Evaluation Engine (Bezier & Stepped Hold)                            */
  /* -------------------------------------------------------------------------- */
  evaluateTrackAtShot(track, shotIndex) {
    if (!track.keyframes || track.keyframes.length === 0) {
      return this.plan.defaults[track.id] || 0.0;
    }

    const sorted = [...track.keyframes].sort((a, b) => a.shotIndex - b.shotIndex);

    if (track.type === "continuous") {
      if (sorted.length === 1) return sorted[0].value;

      let left = sorted[0];
      let right = sorted[sorted.length - 1];

      for (let i = 0; i < sorted.length - 1; i++) {
        if (sorted[i].shotIndex <= shotIndex && sorted[i + 1].shotIndex >= shotIndex) {
          left = sorted[i];
          right = sorted[i + 1];
          break;
        }
      }

      if (left.id === right.id || left.shotIndex === right.shotIndex) {
        return left.value;
      }

      const u = (shotIndex - left.shotIndex) / (right.shotIndex - left.shotIndex);
      let t = u;

      if (left.mode === "linear") {
        t = u;
      } else {
        // Cubic Hermite / Bezier easing
        t = u * u * (3.0 - 2.0 * u);
      }

      return left.value + t * (right.value - left.value);
    } else {
      // Discrete stepped parameter: hold latest keyframe
      let activeVal = sorted[0].value;
      for (const k of sorted) {
        if (k.shotIndex <= shotIndex) {
          activeVal = k.value;
        } else {
          break;
        }
      }
      return activeVal;
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Dynamic Parameter Track Auto-Creation & Auto-Cleanup                       */
  /* -------------------------------------------------------------------------- */
  ensureCameraTrack(paramKey, initialVal) {
    if (!this.plan.tracks[paramKey]) {
      const labels = {
        shutter_speed: "Shutter",
        iso: "ISO",
        aperture: "Aperture",
        white_balance: "White Balance"
      };
      const colors = {
        shutter_speed: "#a855f7",
        iso: "#10b981",
        aperture: "#ec4899",
        white_balance: "#eab308"
      };

      this.plan.tracks[paramKey] = {
        id: paramKey,
        label: labels[paramKey] || paramKey,
        color: colors[paramKey] || "#8b5cf6",
        type: "discrete",
        keyframes: [
          { id: `${paramKey}-start`, shotIndex: 1, value: this.plan.defaults[paramKey] },
          { id: `${paramKey}-${Date.now()}`, shotIndex: this.playhead, value: initialVal }
        ]
      };
      this.activeTrackId = paramKey;
      this.showToast(`Auto-created timeline track: ${labels[paramKey]}`, "info");
    } else {
      const track = this.plan.tracks[paramKey];
      let key = this.getKeyTriggerAtShot(track, this.playhead);
      if (!key) {
        key = { id: `${paramKey}-${Date.now()}`, shotIndex: this.playhead, value: initialVal };
        track.keyframes.push(key);
      } else {
        key.value = initialVal;
      }
      track.keyframes.sort((a, b) => a.shotIndex - b.shotIndex);
    }
  }

  cleanupCameraTrack(paramKey) {
    const track = this.plan.tracks[paramKey];
    if (!track || track.type === "continuous") return;

    if (track.keyframes.length <= 1) {
      delete this.plan.tracks[paramKey];
      if (this.activeTrackId === paramKey) this.activeTrackId = "pan";
      this.renderTrackHeaders();
      this.showToast(`Collapsed timeline track: ${paramKey}`, "info");
      return;
    }

    const firstVal = track.keyframes[0].value;
    const allSame = track.keyframes.every((k) => k.value === firstVal);
    if (allSame) {
      this.plan.defaults[paramKey] = firstVal;
      delete this.plan.tracks[paramKey];
      if (this.activeTrackId === paramKey) this.activeTrackId = "pan";
      this.renderTrackHeaders();
      this.showToast(`Cleaned redundant track: ${paramKey}`, "info");
    }
  }

  renderTrackHeaders() {
    const container = this.dom.timelineHeaders;
    container.innerHTML = '<div class="track-header-ruler">TRIGGER RULER</div>';

    Object.keys(this.plan.tracks).forEach((trackId) => {
      const track = this.plan.tracks[trackId];
      const item = document.createElement("div");
      item.className = `track-header-item ${this.activeTrackId === trackId ? "active" : ""}`;
      item.onclick = () => {
        this.activeTrackId = trackId;
        this.renderTrackHeaders();
        this.updateInspectorUI();
        this.renderTimeline();
      };

      const curVal = this.evaluateTrackAtShot(track, this.playhead);
      const displayVal = track.type === "continuous" ? `${Number(curVal).toFixed(1)}°` : curVal;

      item.innerHTML = `
        <span class="track-label">
          <span class="track-color-indicator ${track.id}"></span>
          ${track.label}
        </span>
        <span style="color: ${track.color}; font-family: var(--font-mono); font-size: 11px;">${displayVal}</span>
      `;
      container.appendChild(item);
    });
  }

  /* -------------------------------------------------------------------------- */
  /* Key Trigger Management                                                     */
  /* -------------------------------------------------------------------------- */
  getKeyTriggerAtShot(track, shotIndex) {
    if (!track?.keyframes) return null;
    return track.keyframes.find((k) => k.shotIndex === shotIndex);
  }

  addKeyTriggerAtPlayhead() {
    const track = this.plan.tracks[this.activeTrackId];
    if (!track) return;

    const existing = this.getKeyTriggerAtShot(track, this.playhead);
    if (existing) {
      this.selectedKeyId = existing.id;
      this.updateInspectorUI();
      return;
    }

    const curVal = this.evaluateTrackAtShot(track, this.playhead);
    const newKey = {
      id: `${track.id}-${Date.now()}`,
      shotIndex: this.playhead,
      value: track.type === "continuous" ? Number(curVal.toFixed(1)) : curVal,
      mode: "auto",
      inTangent: [-15, 0],
      outTangent: [15, 0]
    };

    track.keyframes.push(newKey);
    track.keyframes.sort((a, b) => a.shotIndex - b.shotIndex);
    this.selectedKeyId = newKey.id;

    this.updateInspectorUI();
    this.renderTimeline();
    this.showToast(`Added Key on ${track.label} at Shot ${this.playhead}`, "success");
    this.checkLiveRamping(track.id, newKey.value);
  }

  toggleKeyTriggerAtPlayhead() {
    const track = this.plan.tracks[this.activeTrackId];
    if (!track) return;

    const existing = this.getKeyTriggerAtShot(track, this.playhead);
    if (existing) {
      if (track.type === "continuous" && track.keyframes.length <= 2) {
        this.showToast("Axis tracks must keep at least start and end key triggers", "error");
        return;
      }
      this.deleteKeyTrigger(track.id, existing.id);
    } else {
      this.addKeyTriggerAtPlayhead();
    }
  }

  deleteKeyTrigger(trackId, keyId) {
    const track = this.plan.tracks[trackId];
    if (!track) return;

    track.keyframes = track.keyframes.filter((k) => k.id !== keyId);
    this.selectedKeyId = track.keyframes[0]?.id || null;

    if (track.type === "discrete") {
      this.cleanupCameraTrack(trackId);
    }

    this.updateInspectorUI();
    this.renderTrackHeaders();
    this.renderTimeline();
    this.showToast("Key Trigger removed");
    this.checkLiveRamping(trackId, null);
  }

  goToPrevKey() {
    const track = this.plan.tracks[this.activeTrackId];
    if (!track) return;
    const before = track.keyframes.filter((k) => k.shotIndex < this.playhead);
    if (before.length > 0) {
      const prev = before[before.length - 1];
      this.selectedKeyId = prev.id;
      this.setPlayhead(prev.shotIndex);
    }
  }

  goToNextKey() {
    const track = this.plan.tracks[this.activeTrackId];
    if (!track) return;
    const after = track.keyframes.filter((k) => k.shotIndex > this.playhead);
    if (after.length > 0) {
      const next = after[0];
      this.selectedKeyId = next.id;
      this.setPlayhead(next.shotIndex);
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Inspector Synchronization & Auto-Synced Live Jogging                       */
  /* -------------------------------------------------------------------------- */
  updateInspectorUI() {
    const track = this.plan.tracks[this.activeTrackId];
    if (!track) return;

    this.dom.inspectorTrackTitle.textContent = `📍 Key Trigger: ${track.label}`;
    const key = this.getKeyTriggerAtShot(track, this.playhead);

    if (track.type === "continuous") {
      this.dom.numericValueGroup.style.display = "flex";
      this.dom.discreteValueGroup.style.display = "none";
      this.dom.easingContainer.style.display = "block";
      this.dom.lblParameterValue.textContent = `Target ${track.label}`;
      this.dom.numericInputUnit.textContent = "deg";

      const val = key ? key.value : this.evaluateTrackAtShot(track, this.playhead);
      this.dom.keyNumericInput.value = Number(val).toFixed(1);
      this.dom.keyEasingSelect.value = key?.mode || "auto";
    } else {
      this.dom.numericValueGroup.style.display = "none";
      this.dom.discreteValueGroup.style.display = "block";
      this.dom.easingContainer.style.display = "none";
      this.dom.lblParameterValue.textContent = `Target ${track.label} (Hold Step)`;

      const choices = this.cameraChoices[track.id] || [];
      this.dom.keyDiscreteSelect.innerHTML = "";
      choices.forEach((c) => {
        const opt = document.createElement("option");
        opt.value = c;
        opt.textContent = c;
        this.dom.keyDiscreteSelect.appendChild(opt);
      });
      const val = key ? key.value : this.evaluateTrackAtShot(track, this.playhead);
      this.dom.keyDiscreteSelect.value = val;
    }

    if (key) {
      this.dom.keyTriggerCard.className = "key-trigger-card is-key";
      const keyIdx = track.keyframes.findIndex((k) => k.id === key.id) + 1;
      this.dom.keyCardTitle.textContent = `Key Trigger #${keyIdx} (Shot ${key.shotIndex})`;
      this.dom.btnToggleKeyTrigger.textContent = "Remove Key";
      this.dom.btnToggleKeyTrigger.className = "btn btn-danger btn-sm";
    } else {
      this.dom.keyTriggerCard.className = "key-trigger-card";
      this.dom.keyCardTitle.textContent = `Shot ${this.playhead} (Interpolated)`;
      this.dom.btnToggleKeyTrigger.textContent = "+ Key Here";
      this.dom.btnToggleKeyTrigger.className = "btn btn-primary btn-sm";
    }

    this.renderTrackHeaders();
  }

  updateOverlays() {
    const pan = this.evaluateTrackAtShot(this.plan.tracks.pan, this.playhead);
    const tilt = this.evaluateTrackAtShot(this.plan.tracks.tilt, this.playhead);
    const shutter = this.evaluateTrackAtShot(this.plan.tracks.shutter_speed || { id: "shutter_speed" }, this.playhead);
    const iso = this.evaluateTrackAtShot(this.plan.tracks.iso || { id: "iso" }, this.playhead);
    const aperture = this.evaluateTrackAtShot(this.plan.tracks.aperture || { id: "aperture" }, this.playhead);
    const wb = this.evaluateTrackAtShot(this.plan.tracks.white_balance || { id: "white_balance" }, this.playhead);

    this.dom.shotCounterOverlay.textContent = `Shot ${this.playhead} / ${this.plan.totalShots}`;
    this.dom.interpolatedPoseOverlay.textContent =
      `Pan: ${Number(pan).toFixed(1)}° | Tilt: ${Number(tilt).toFixed(1)}° | ISO ${iso} | ${shutter}s | f/${aperture} | ${wb}`;
  }

  setPlayhead(shotIndex, updateInput = true) {
    this.playhead = Math.max(1, Math.min(this.plan.totalShots, shotIndex));
    if (updateInput) this.dom.playheadInput.value = this.playhead;

    const track = this.plan.tracks[this.activeTrackId];
    if (track) {
      const key = this.getKeyTriggerAtShot(track, this.playhead);
      if (key) this.selectedKeyId = key.id;
    }

    this.updateInspectorUI();
    this.updateOverlays();
    this.renderTimeline();
  }

  /* Auto-Synced Jogging: Moves rig & syncs directly into active keypoint */
  async jogMotor(panDelta, tiltDelta) {
    try {
      await fetch("/api/motors/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pan: panDelta, tilt: tiltDelta, relative: true })
      });

      // Update Pan track
      if (panDelta !== 0) {
        let key = this.getKeyTriggerAtShot(this.plan.tracks.pan, this.playhead);
        if (!key) {
          this.activeTrackId = "pan";
          this.addKeyTriggerAtPlayhead();
          key = this.getKeyTriggerAtShot(this.plan.tracks.pan, this.playhead);
        }
        if (key) key.value = Number((key.value + panDelta).toFixed(1));
      }

      // Update Tilt track
      if (tiltDelta !== 0) {
        let key = this.getKeyTriggerAtShot(this.plan.tracks.tilt, this.playhead);
        if (!key) {
          this.activeTrackId = "tilt";
          this.addKeyTriggerAtPlayhead();
          key = this.getKeyTriggerAtShot(this.plan.tracks.tilt, this.playhead);
        }
        if (key) key.value = Math.max(-80, Math.min(80, Number((key.value + tiltDelta).toFixed(1))));
      }

      this.updateInspectorUI();
      this.updateOverlays();
      this.renderTimeline();
      this.showToast(`Auto-synced jog: Pan ${panDelta > 0 ? "+" : ""}${panDelta}°, Tilt ${tiltDelta > 0 ? "+" : ""}${tiltDelta}°`, "info");
    } catch (e) {
      this.showToast(`Jog error: ${e}`, "error");
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Shutter Speed vs. Interval Safety Check (+3s Download Buffer)             */
  /* -------------------------------------------------------------------------- */
  parseShutterSeconds(shutterStr) {
    if (!shutterStr) return 0.004;
    const s = shutterStr.toString().trim();
    if (s.includes("/")) {
      const parts = s.split("/");
      return parseFloat(parts[0]) / parseFloat(parts[1]);
    }
    return parseFloat(s) || 0.004;
  }

  checkShutterIntervalSafety() {
    let longestShutter = this.parseShutterSeconds(this.plan.defaults.shutter_speed);
    if (this.plan.tracks.shutter_speed) {
      this.plan.tracks.shutter_speed.keyframes.forEach((k) => {
        const sec = this.parseShutterSeconds(k.value);
        if (sec > longestShutter) longestShutter = sec;
      });
    }

    const required = longestShutter + this.plan.settle_time_s + 3.0; // +3s download buffer
    const banner = this.dom.intervalWarningBanner;

    if (required > this.plan.interval_s) {
      this.recommendedInterval = Math.ceil(required);
      this.dom.intervalWarningText.textContent =
        `⚠️ Longest shutter (${longestShutter}s) + settle (${this.plan.settle_time_s}s) + 3s buffer = ${required.toFixed(1)}s exceeds interval (${this.plan.interval_s}s)!`;
      banner.style.display = "flex";
    } else {
      banner.style.display = "none";
    }
  }

  autoAdjustInterval() {
    if (this.recommendedInterval) {
      this.plan.interval_s = this.recommendedInterval;
      this.dom.intervalInput.value = this.recommendedInterval;
      this.updateScheduleCalculations();
      this.checkShutterIntervalSafety();
      this.showToast(`Interval adjusted to safe ${this.recommendedInterval}s`, "success");
    }
  }

  setTotalShots(total) {
    const oldTotal = this.plan.totalShots;
    this.plan.totalShots = total;
    this.dom.totalShotsLabel.textContent = total;
    this.dom.playheadInput.max = total;

    Object.values(this.plan.tracks).forEach((track) => {
      const lastKey = track.keyframes[track.keyframes.length - 1];
      if (lastKey && lastKey.shotIndex === oldTotal) {
        lastKey.shotIndex = total;
      }
    });

    this.updateScheduleCalculations();
    this.setPlayhead(Math.min(this.playhead, total));
    this.renderTimeline();
  }

  updateScheduleCalculations() {
    const total = this.plan.totalShots;
    const interval = this.plan.interval_s;
    const totalSecs = total * interval;
    const mins = Math.floor(totalSecs / 60);
    const secs = Math.floor(totalSecs % 60);
    const runTimeStr = `${mins}m ${secs.toString().padStart(2, "0")}s`;
    this.dom.calcRunTime.textContent = runTimeStr;
    this.dom.timingOverlay.textContent = `ETA: ${runTimeStr}`;

    const clipLength = (total / 24).toFixed(1);
    this.dom.calcClipLength.textContent = `${clipLength}s`;
  }

  /* -------------------------------------------------------------------------- */
  /* Live In-Run Ramping & Discrete Offset Dialog                               */
  /* -------------------------------------------------------------------------- */
  checkLiveRamping(paramKey, newVal) {
    if (this.liveState.timelapse.state !== "RUNNING") return;

    const track = this.plan.tracks[paramKey];
    if (track && track.type === "discrete" && track.keyframes.length > 1) {
      // Future keys exist; prompt user for offset choice
      const curIdx = this.liveState.timelapse.current_shot;
      const futureKeys = track.keyframes.filter((k) => k.shotIndex > curIdx);
      if (futureKeys.length > 0) {
        this.pendingOffsetChange = { paramKey, newVal };
        this.dom.offsetPromptText.textContent =
          `You adjusted ${track.label} during an active sequence. Apply as a hold from next shot, or shift all ${futureKeys.length} upcoming key triggers by relative stops?`;
        this.dom.offsetChoiceModal.style.display = "flex";
        return;
      }
    }

    // Direct hot-update
    this.sendHotUpdate();
  }

  applyOffsetChoice(choice) {
    this.dom.offsetChoiceModal.style.display = "none";
    if (!this.pendingOffsetChange) return;

    const { paramKey, newVal } = this.pendingOffsetChange;
    const track = this.plan.tracks[paramKey];

    if (choice === "shift_all" && track && track.type === "discrete") {
      const choices = this.cameraChoices[paramKey] || [];
      const curIdx = this.liveState.timelapse.current_shot;
      const oldVal = track.keyframes.find((k) => k.shotIndex <= curIdx)?.value || this.plan.defaults[paramKey];
      const oldStopIdx = choices.indexOf(oldVal);
      const newStopIdx = choices.indexOf(newVal);
      const stopDelta = newStopIdx - oldStopIdx;

      track.keyframes.forEach((k) => {
        if (k.shotIndex > curIdx) {
          const kIdx = choices.indexOf(k.value);
          const targetIdx = Math.max(0, Math.min(choices.length - 1, kIdx + stopDelta));
          k.value = choices[targetIdx];
        }
      });
      this.showToast(`Shifted upcoming ${track.label} keys by ${stopDelta > 0 ? "+" : ""}${stopDelta} stops`, "success");
    }

    this.sendHotUpdate();
    this.pendingOffsetChange = null;
    this.renderTimeline();
  }

  async sendHotUpdate() {
    const total = this.plan.totalShots;
    const poses = [];
    const camera_settings = [];

    for (let s = 1; s <= total; s++) {
      const pan = this.evaluateTrackAtShot(this.plan.tracks.pan, s);
      const tilt = this.evaluateTrackAtShot(this.plan.tracks.tilt, s);
      const shutter = this.evaluateTrackAtShot(this.plan.tracks.shutter_speed || { id: "shutter_speed" }, s);
      const iso = this.evaluateTrackAtShot(this.plan.tracks.iso || { id: "iso" }, s);
      const aperture = this.evaluateTrackAtShot(this.plan.tracks.aperture || { id: "aperture" }, s);
      const wb = this.evaluateTrackAtShot(this.plan.tracks.white_balance || { id: "white_balance" }, s);

      poses.push({ pan: Number(Number(pan).toFixed(2)), tilt: Number(Number(tilt).toFixed(2)) });
      camera_settings.push({
        iso: String(iso),
        shutter_speed: String(shutter),
        aperture: String(aperture),
        white_balance: String(wb)
      });
    }

    try {
      const res = await fetch("/api/timelapse/adjust", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ poses, camera_settings })
      });
      if (res.ok) {
        this.showToast("Hot-updated active time-lapse targets", "info");
      }
    } catch (e) {
      console.warn("Hot update failed", e);
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Focus Station & 5x Focus Loupe (Night/Astrophotography)                    */
  /* -------------------------------------------------------------------------- */
  async triggerAutoFocus() {
    this.showToast("Acquiring Autofocus lock...");
    try {
      const res = await fetch("/api/camera/focus/autofocus", { method: "POST" });
      const data = await res.json();
      if (data.status === "OK") this.showToast("Autofocus locked", "success");
      else this.showToast(`Autofocus: ${data.message}`, "warning");
    } catch (e) {
      this.showToast(`AF error: ${e}`, "error");
    }
  }

  async stepFocus(direction, stepSize) {
    this.showToast(`Focus stepping ${direction} (${stepSize})...`);
    try {
      const res = await fetch("/api/camera/focus/step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ direction, step_size: stepSize })
      });
      const data = await res.json();
      if (data.status === "OK") {
        this.showToast(`Focus stepped ${direction} ${stepSize}`, "success");
      } else {
        this.showToast(`Focus: ${data.message}`, "warning");
      }
    } catch (e) {
      this.showToast(`Focus error: ${e}`, "error");
    }
  }

  toggleLoupe() {
    this.isLoupeActive = !this.isLoupeActive;
    this.dom.btnToggleLoupe.classList.toggle("btn-primary", this.isLoupeActive);
    this.dom.viewportContainer.classList.toggle("loupe-active", this.isLoupeActive);
    if (!this.isLoupeActive && this.dom.loupeOverlay) {
      this.dom.loupeOverlay.style.display = "none";
    }
    this.showToast(this.isLoupeActive ? "5x Loupe ON: Hover over viewport to inspect star focus" : "5x Loupe OFF");
  }

  onViewportMouseMove(e) {
    if (!this.isLoupeActive || !this.dom.previewImage || this.dom.previewImage.style.display === "none") return;

    const loupe = this.dom.loupeOverlay;
    const img = this.dom.previewImage;
    const rect = img.getBoundingClientRect();
    const containerRect = this.dom.viewportContainer.getBoundingClientRect();

    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    if (mouseX < 0 || mouseX > rect.width || mouseY < 0 || mouseY > rect.height) {
      loupe.style.display = "none";
      return;
    }

    loupe.style.display = "block";
    const loupeX = e.clientX - containerRect.left - 70;
    const loupeY = e.clientY - containerRect.top - 70;
    loupe.style.left = `${loupeX}px`;
    loupe.style.top = `${loupeY}px`;

    const zoomFactor = 4;
    loupe.style.backgroundImage = `url(${img.src})`;
    loupe.style.backgroundSize = `${rect.width * zoomFactor}px ${rect.height * zoomFactor}px`;
    loupe.style.backgroundPosition = `-${mouseX * zoomFactor - 70}px -${mouseY * zoomFactor - 70}px`;
  }

  async takeStarSnap() {
    this.showToast("Capturing fast high-gain Star Snap (ISO 12800, 2.5s)...");
    try {
      const res = await fetch("/api/camera/trigger", { method: "POST" });
      const data = await res.json();
      if (data.status === "OK") {
        this.dom.previewImage.src = `/api/camera/preview/latest?t=${Date.now()}`;
        this.dom.previewImage.style.display = "block";
        this.dom.viewportPlaceholder.style.display = "none";
        this.showToast("Star Snap captured! Inspect sharpness with 5x Loupe", "success");
      } else {
        this.showToast(`Star Snap failed: ${data.message}`, "error");
      }
    } catch (e) {
      this.showToast(`Star Snap error: ${e}`, "error");
    }
  }

  async takeSnapshot() {
    this.showToast("Capturing snapshot exposure...");
    try {
      const res = await fetch("/api/camera/trigger", { method: "POST" });
      const data = await res.json();
      if (data.status === "OK") {
        this.dom.previewImage.src = `/api/camera/preview/latest?t=${Date.now()}`;
        this.dom.previewImage.style.display = "block";
        this.dom.viewportPlaceholder.style.display = "none";
        this.showToast("Snapshot captured", "success");
      } else {
        this.showToast(`Snapshot: ${data.message}`, "error");
      }
    } catch (e) {
      this.showToast(`Snapshot error: ${e}`, "error");
    }
  }

  async toggleLiveView() {
    this.isLiveViewActive = !this.isLiveViewActive;
    if (this.isLiveViewActive) {
      this.dom.btnToggleLiveView.textContent = "🎥 Live Stream: ON";
      this.dom.btnToggleLiveView.classList.add("btn-primary");
      this.dom.previewImage.src = `/api/camera/preview/stream?t=${Date.now()}`;
      this.dom.previewImage.style.display = "block";
      this.dom.viewportPlaceholder.style.display = "none";
    } else {
      this.dom.btnToggleLiveView.textContent = "🎥 Live Stream: OFF";
      this.dom.btnToggleLiveView.classList.remove("btn-primary");
      this.dom.previewImage.src = "/api/camera/preview/latest";
    }
  }

  async commandRigToPlayheadPose() {
    const pan = this.evaluateTrackAtShot(this.plan.tracks.pan, this.playhead);
    const tilt = this.evaluateTrackAtShot(this.plan.tracks.tilt, this.playhead);
    this.showToast(`Moving rig to (${Number(pan).toFixed(1)}°, ${Number(tilt).toFixed(1)}°)...`);

    try {
      const res = await fetch("/api/motors/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pan, tilt, relative: false })
      });
      const data = await res.json();
      if (data.status === "OK") this.showToast("Rig moved successfully", "success");
      else this.showToast(`Move rejected: ${data.message}`, "error");
    } catch (e) {
      this.showToast(`Move error: ${e}`, "error");
    }
  }

  async restartCamera() {
    this.showToast("Restarting camera session...");
    try {
      const res = await fetch("/api/camera/restart", { method: "POST" });
      const data = await res.json();
      if (data.status === "OK") this.showToast("Camera session restarted", "success");
      else this.showToast(`Camera restart failed: ${data.message}`, "error");
    } catch (e) {
      this.showToast(`Camera error: ${e}`, "error");
    }
  }

  async syncFromCameraSettings() {
    try {
      const res = await fetch("/api/camera/status");
      if (res.ok) {
        const data = await res.json();
        if (data.iso) this.plan.defaults.iso = data.iso;
        if (data.shutter_speed) this.plan.defaults.shutter_speed = data.shutter_speed;
        if (data.aperture) this.plan.defaults.aperture = data.aperture;
        if (data.white_balance) this.plan.defaults.white_balance = data.white_balance;
        this.populateSelectOptions();
        this.updateOverlays();
        this.showToast("Synced camera settings as defaults", "success");
      }
    } catch (e) {
      this.showToast(`Camera sync error: ${e}`, "error");
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Virtual Preview Playback                                                   */
  /* -------------------------------------------------------------------------- */
  togglePreviewPlayback() {
    if (this.isPlayingPreview) {
      this.stopPreviewPlayback();
    } else {
      this.startPreviewPlayback();
    }
  }

  startPreviewPlayback() {
    this.isPlayingPreview = true;
    this.dom.btnPlayPreview.textContent = "⏸ Pause";
    this.dom.btnPlayPreview.classList.add("btn-danger");

    if (this.playhead >= this.plan.totalShots) this.setPlayhead(1);

    this.previewIntervalId = setInterval(() => {
      if (this.playhead < this.plan.totalShots) {
        this.setPlayhead(this.playhead + 1);
      } else {
        this.stopPreviewPlayback();
      }
    }, 45); // ~22 fps preview scrub
  }

  stopPreviewPlayback() {
    this.isPlayingPreview = false;
    if (this.previewIntervalId) {
      clearInterval(this.previewIntervalId);
      this.previewIntervalId = null;
    }
    this.dom.btnPlayPreview.textContent = "▶ Preview";
    this.dom.btnPlayPreview.classList.remove("btn-danger");
  }

  /* -------------------------------------------------------------------------- */
  /* Sequence Execution (Start, Pause, Resume, Emergency Stop)                  */
  /* -------------------------------------------------------------------------- */
  async startTimelapse() {
    const total = this.plan.totalShots;
    const interval = this.plan.interval_s;

    const poses = [];
    const camera_settings = [];

    for (let s = 1; s <= total; s++) {
      const pan = this.evaluateTrackAtShot(this.plan.tracks.pan, s);
      const tilt = this.evaluateTrackAtShot(this.plan.tracks.tilt, s);
      const shutter = this.evaluateTrackAtShot(this.plan.tracks.shutter_speed || { id: "shutter_speed" }, s);
      const iso = this.evaluateTrackAtShot(this.plan.tracks.iso || { id: "iso" }, s);
      const aperture = this.evaluateTrackAtShot(this.plan.tracks.aperture || { id: "aperture" }, s);
      const wb = this.evaluateTrackAtShot(this.plan.tracks.white_balance || { id: "white_balance" }, s);

      poses.push({ pan: Number(Number(pan).toFixed(2)), tilt: Number(Number(tilt).toFixed(2)) });
      camera_settings.push({
        iso: String(iso),
        shutter_speed: String(shutter),
        aperture: String(aperture),
        white_balance: String(wb)
      });
    }

    const payload = {
      plan_name: this.dom.planNameInput.value || "Timeline Sequence",
      total_shots: total,
      interval_s: interval,
      settle_time_s: this.plan.settle_time_s,
      capture_photo: true,
      poses,
      camera_settings
    };

    this.showToast("Initiating time-lapse sequence...");
    try {
      const res = await fetch("/api/timelapse/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.status === "OK") this.showToast("Time-lapse sequence started!", "success");
      else this.showToast(`Start failed: ${data.message}`, "error");
    } catch (e) {
      this.showToast(`Start error: ${e}`, "error");
    }
  }

  async pauseOrResumeTimelapse() {
    const currentState = this.liveState.timelapse.state;
    if (currentState === "RUNNING") {
      await fetch("/api/timelapse/pause", { method: "POST" });
      this.showToast("Time-lapse paused");
    } else if (currentState === "PAUSED") {
      await fetch("/api/timelapse/resume", { method: "POST" });
      this.showToast("Time-lapse resumed", "success");
    }
  }

  async emergencyStop() {
    this.showToast("Sending STOP command...");
    try {
      await fetch("/api/timelapse/cancel", { method: "POST" });
      await fetch("/api/motors/stop", { method: "POST" });
      this.showToast("Operation cancelled & motors stopped", "warning");
    } catch (e) {
      this.showToast(`Stop error: ${e}`, "error");
    }
  }

  async savePlan() {
    const planName = this.dom.planNameInput.value.trim() || "Timeline Plan";
    localStorage.setItem("pantiltlapse_saved_plan", JSON.stringify(this.plan));
    this.showToast(`Plan "${planName}" saved locally`, "success");
  }

  showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    this.dom.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3500);
  }
}

// Global initialization
document.addEventListener("DOMContentLoaded", () => {
  window.app = new TimelineStudioApp();
});

// Global window helpers for legacy compatibility & modals
window.goHome = async function() {
  if (window.app) {
    window.app.showToast("Returning rig to (0.00°, 0.00°)...");
    try {
      await fetch("/api/motors/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pan: 0.0, tilt: 0.0, relative: false })
      });
      window.app.setPlayhead(1);
    } catch (e) {
      window.app.showToast(`Go Home error: ${e}`, "error");
    }
  }
};

window.openRecalibrateModal = function() {
  const m = document.getElementById("recalibrateModal");
  if (m) m.style.display = "flex";
};

window.closeRecalibrateModal = function() {
  const m = document.getElementById("recalibrateModal");
  if (m) m.style.display = "none";
};

window.executeRecalibrateZero = async function() {
  window.closeRecalibrateModal();
  try {
    const res = await fetch("/api/rig/confirm-zero", { method: "POST" });
    const data = await res.json();
    if (data.status === "OK") {
      if (window.app) window.app.showToast("Zero reference confirmed (0°, 0°)", "success");
    } else {
      if (window.app) window.app.showToast(`Zero confirmation failed: ${data.message}`, "error");
    }
  } catch (e) {
    if (window.app) window.app.showToast(`Zero error: ${e}`, "error");
  }
};

window.closeOffsetChoiceModal = function() {
  const m = document.getElementById("offsetChoiceModal");
  if (m) m.style.display = "none";
};
