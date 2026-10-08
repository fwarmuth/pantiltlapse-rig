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
        white_balance: "Auto",
        raw: false,
        image_format: "L"
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
    this.imageTier = localStorage.getItem("pantiltlapse_image_quality") || "low";

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

    // Viewport Mode Tabs & Test Shots
    this.activeViewportTab = "timelapse";
    this.testShots = [];
    this.selectedTestShot = null;

    // Decoupled Live Execution Tracking
    this.followLive = true;
    this.liveShot = 1;
    this.capturedShotsMap = new Map(); // shotIndex -> filename

    // Plan Storage Tracking
    this.currentPlanId = null;
    this.currentPlanRevision = 1;

    this.initDOM();
    this.bindEvents();
    this.initCanvas();
    this.fetchCameraChoices();
    this.fetchInitialRigStatus();
    this.fetchTestShots();
    this.initSSE();
    this.loadInitialPlan();
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
      btnOpenPlan: document.getElementById("btnOpenPlan"),
      openPlanModal: document.getElementById("openPlanModal"),
      savedPlansList: document.getElementById("savedPlansList"),
      btnRefreshPlansList: document.getElementById("btnRefreshPlansList"),
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
      tabBtnTimelapse: document.getElementById("tabBtnTimelapse"),
      tabBtnTestShots: document.getElementById("tabBtnTestShots"),
      testShotsCountBadge: document.getElementById("testShotsCountBadge"),
      testShotsHeaderActions: document.getElementById("testShotsHeaderActions"),
      btnRefreshTestShots: document.getElementById("btnRefreshTestShots"),
      btnDeleteSelectedTestShot: document.getElementById("btnDeleteSelectedTestShot"),
      btnDeleteAllTestShots: document.getElementById("btnDeleteAllTestShots"),
      btnDeleteAllTestShotsBar: document.getElementById("btnDeleteAllTestShotsBar"),
      timelapseControlsWrapper: document.getElementById("timelapseControlsWrapper"),
      testShotsControlsWrapper: document.getElementById("testShotsControlsWrapper"),
      testShotsFilmstrip: document.getElementById("testShotsFilmstrip"),
      selectedShotLabel: document.getElementById("selectedShotLabel"),
      testShotMetaPill: document.getElementById("testShotMetaPill"),
      testShotMetaText: document.getElementById("testShotMetaText"),
      viewportPlaceholderText: document.getElementById("viewportPlaceholderText"),
      btnStarSnapTestShots: document.getElementById("btnStarSnapTestShots"),
      btnTakeSnapshotTestShots: document.getElementById("btnTakeSnapshotTestShots"),
      btnToggleLoupeTestShots: document.getElementById("btnToggleLoupeTestShots"),

      viewportContainer: document.getElementById("viewportContainer"),
      previewImage: document.getElementById("previewImage"),
      loupeOverlay: document.getElementById("loupeOverlay"),
      viewportPlaceholder: document.getElementById("viewportPlaceholder"),
      shotCounterOverlay: document.getElementById("shotCounterOverlay"),
      timingOverlay: document.getElementById("timingOverlay"),
      interpolatedPoseOverlay: document.getElementById("interpolatedPoseOverlay"),
      exposureCountdownOverlay: document.getElementById("exposureCountdownOverlay"),
      exposureTitle: document.getElementById("exposureTitle"),
      exposureTimer: document.getElementById("exposureTimer"),
      exposureProgressFill: document.getElementById("exposureProgressFill"),
      exposureDetails: document.getElementById("exposureDetails"),
      latestPhotoPill: document.getElementById("latestPhotoPill"),
      latestPhotoText: document.getElementById("latestPhotoText"),
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

      // Key Trigger Inspector & Direct Angles
      inspectorTrackTitle: document.getElementById("inspectorTrackTitle"),
      keyTriggerCard: document.getElementById("keyTriggerCard"),
      keyCardTitle: document.getElementById("keyCardTitle"),
      btnToggleKeyTrigger: document.getElementById("btnToggleKeyTrigger"),
      keyAnglesPanel: document.getElementById("keyAnglesPanel"),
      keyPanInput: document.getElementById("keyPanInput"),
      panKeyIndicator: document.getElementById("panKeyIndicator"),
      keyTiltInput: document.getElementById("keyTiltInput"),
      tiltKeyIndicator: document.getElementById("tiltKeyIndicator"),
      btnDriveRigToPose: document.getElementById("btnDriveRigToPose"),
      parameterValueContainer: document.getElementById("parameterValueContainer"),
      lblParameterValue: document.getElementById("lblParameterValue"),
      discreteValueGroup: document.getElementById("discreteValueGroup"),
      keyDiscreteSelect: document.getElementById("keyDiscreteSelect"),
      easingContainer: document.getElementById("easingContainer"),
      keyEasingSelect: document.getElementById("keyEasingSelect"),

      // Defaults
      btnSyncFromCam: document.getElementById("btnSyncFromCam"),
      cameraTrackContextBadge: document.getElementById("cameraTrackContextBadge"),
      defaultIsoSelect: document.getElementById("defaultIsoSelect"),
      defaultShutterSelect: document.getElementById("defaultShutterSelect"),
      defaultApertureSelect: document.getElementById("defaultApertureSelect"),
      defaultWbSelect: document.getElementById("defaultWbSelect"),
      chkCaptureRaw: document.getElementById("chkCaptureRaw"),
      rawFormatBadge: document.getElementById("rawFormatBadge"),

      // Timeline Toolbar
      btnFirstShot: document.getElementById("btnFirstShot"),
      btnPrevKey: document.getElementById("btnPrevKey"),
      btnPlayPreview: document.getElementById("btnPlayPreview"),
      btnNextKey: document.getElementById("btnNextKey"),
      btnLastShot: document.getElementById("btnLastShot"),
      playheadInput: document.getElementById("playheadInput"),
      totalShotsLabel: document.getElementById("totalShotsLabel"),
      btnAddKeyTrigger: document.getElementById("btnAddKeyTrigger"),
      btnAddTrackMenuBtn: document.getElementById("btnAddTrackMenuBtn"),
      addTrackDropdown: document.getElementById("addTrackDropdown"),
      zoomSlider: document.getElementById("zoomSlider"),
      btnToggleCurveGraph: document.getElementById("btnToggleCurveGraph"),
      followLiveToggleLabel: document.getElementById("followLiveToggleLabel"),
      chkFollowLive: document.getElementById("chkFollowLive"),
      btnToggleFollowLive: document.getElementById("btnToggleFollowLive"),
      followLiveDot: document.getElementById("followLiveDot"),
      followLiveLabel: document.getElementById("followLiveLabel"),

      // Detached Live Pill Overlay
      detachedLivePill: document.getElementById("detachedLivePill"),
      detachedEditShot: document.getElementById("detachedEditShot"),
      detachedLiveShot: document.getElementById("detachedLiveShot"),
      btnJumpToLive: document.getElementById("btnJumpToLive"),

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

    // Sequence Camera Defaults & Key Trigger Auto-Creation
    const updateDefault = async (param, val) => {
      if (this.playhead === 1) {
        this.plan.defaults[param] = val;
        // If a track already exists for this parameter, update its shot 1 keyframe
        const track = this.plan.tracks[param];
        if (track) {
          const k1 = track.keyframes.find((k) => k.shotIndex === 1);
          if (k1) {
            k1.value = val;
          }
          this.cleanupCameraTrack(param);
        }
        this.checkShutterIntervalSafety();
        this.updateOverlays();
        this.renderTimeline();
        this.renderTrackHeaders();
        this.updateInspectorUI();
        this.checkLiveRamping(param, val);

        // If camera connected and not running a sequence, push setting to camera immediately
        if (this.liveState.timelapse.state !== "RUNNING") {
          try {
            await fetch("/api/camera/config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ [param]: String(val) })
            });
            if (this.liveState.camera) {
              this.liveState.camera[param] = String(val);
            }
          } catch (_) {}
        }
      } else {
        // Intermediate shot: auto-create or update key trigger on parameter track
        this.ensureCameraTrack(param, val);
        this.renderTrackHeaders();
        this.updateInspectorUI();
        this.renderTimeline();
        this.updateOverlays();
        this.checkShutterIntervalSafety();
        this.checkLiveRamping(param, val);
        const labels = {
          shutter_speed: "Shutter",
          iso: "ISO",
          aperture: "Aperture",
          white_balance: "White Balance"
        };
        this.showToast(`Set ${labels[param] || param} key trigger at Shot ${this.playhead}: ${val}`, "success");
      }
    };
    this.dom.defaultIsoSelect.addEventListener("change", (e) => updateDefault("iso", e.target.value));
    this.dom.defaultShutterSelect.addEventListener("change", (e) => updateDefault("shutter_speed", e.target.value));
    this.dom.defaultApertureSelect.addEventListener("change", (e) => updateDefault("aperture", e.target.value));
    this.dom.defaultWbSelect.addEventListener("change", (e) => updateDefault("white_balance", e.target.value));
    if (this.dom.chkCaptureRaw) {
      this.dom.chkCaptureRaw.addEventListener("change", (e) => this.setRawCapture(e.target.checked));
    }
    this.dom.btnSyncFromCam.addEventListener("click", () => this.syncFromCameraSettings());

    // Direct Keyframe Angle Input Events (Software Only - No Motor Movement)
    this.dom.keyPanInput.addEventListener("input", (e) => this.setKeyAngle("pan", e.target.value));
    this.dom.keyTiltInput.addEventListener("input", (e) => this.setKeyAngle("tilt", e.target.value));

    this.dom.keyDiscreteSelect.addEventListener("change", async (e) => {
      const paramKey = this.activeTrackId;
      const val = e.target.value;
      this.ensureCameraTrack(paramKey, val);
      this.renderTrackHeaders();
      this.updateInspectorUI();
      this.renderTimeline();
      this.updateOverlays();
      this.checkShutterIntervalSafety();
      this.checkLiveRamping(paramKey, val);

      if (this.liveState.timelapse.state !== "RUNNING") {
        try {
          await fetch("/api/camera/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ [paramKey]: String(val) })
          });
          if (this.liveState.camera) {
            this.liveState.camera[paramKey] = String(val);
          }
        } catch (_) {}
      }
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

    // + Track Dropdown Toggle & Selection
    if (this.dom.btnAddTrackMenuBtn && this.dom.addTrackDropdown) {
      this.dom.btnAddTrackMenuBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        const isOpen = this.dom.addTrackDropdown.style.display === "flex";
        this.dom.addTrackDropdown.style.display = isOpen ? "none" : "flex";
      });

      document.addEventListener("click", (e) => {
        if (this.dom.addTrackDropdown && !this.dom.addTrackDropdown.contains(e.target) && e.target !== this.dom.btnAddTrackMenuBtn) {
          this.dom.addTrackDropdown.style.display = "none";
        }
      });

      this.dom.addTrackDropdown.querySelectorAll(".track-menu-item").forEach((btn) => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          this.dom.addTrackDropdown.style.display = "none";
          const param = btn.dataset.param;
          if (param) {
            const currentVal = this.evaluateTrackAtShot(this.plan.tracks[param] || { id: param }, this.playhead);
            this.ensureCameraTrack(param, currentVal);
            this.renderTrackHeaders();
            this.updateInspectorUI();
            this.renderTimeline();
            this.updateOverlays();
          }
        });
      });
    }

    // Transport buttons
    this.dom.btnFirstShot.addEventListener("click", () => {
      this.detachFollowLiveIfRunning();
      this.setPlayhead(1);
    });
    this.dom.btnLastShot.addEventListener("click", () => {
      this.detachFollowLiveIfRunning();
      this.setPlayhead(this.plan.totalShots);
    });
    this.dom.btnPrevKey.addEventListener("click", () => this.goToPrevKey());
    this.dom.btnNextKey.addEventListener("click", () => this.goToNextKey());
    this.dom.btnPlayPreview.addEventListener("click", () => this.togglePreviewPlayback());

    this.dom.playheadInput.addEventListener("change", (e) => {
      this.detachFollowLiveIfRunning();
      this.setPlayhead(parseInt(e.target.value) || 1);
    });

    if (this.dom.chkFollowLive) {
      this.dom.chkFollowLive.addEventListener("change", (e) => {
        this.followLive = e.target.checked;
        if (this.followLive && this.liveShot > 0) {
          this.setPlayhead(this.liveShot, true, true);
        }
        this.updateLiveTrackingUI();
        this.renderTimeline();
      });
    }

    if (this.dom.btnToggleFollowLive) {
      this.dom.btnToggleFollowLive.addEventListener("click", () => this.toggleFollowLive());
    }
    if (this.dom.btnJumpToLive) {
      this.dom.btnJumpToLive.addEventListener("click", () => this.jumpToLive());
    }

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

    // Viewport Mode Tabs
    if (this.dom.tabBtnTimelapse) {
      this.dom.tabBtnTimelapse.addEventListener("click", () => this.switchViewportTab("timelapse"));
    }
    if (this.dom.tabBtnTestShots) {
      this.dom.tabBtnTestShots.addEventListener("click", () => this.switchViewportTab("test-shots"));
    }
    if (this.dom.btnRefreshTestShots) {
      this.dom.btnRefreshTestShots.addEventListener("click", () => this.fetchTestShots(false));
    }
    if (this.dom.btnDeleteSelectedTestShot) {
      this.dom.btnDeleteSelectedTestShot.addEventListener("click", () => this.deleteSelectedTestShot());
    }
    if (this.dom.btnDeleteAllTestShots) {
      this.dom.btnDeleteAllTestShots.addEventListener("click", () => this.deleteAllTestShots());
    }
    if (this.dom.btnDeleteAllTestShotsBar) {
      this.dom.btnDeleteAllTestShotsBar.addEventListener("click", () => this.deleteAllTestShots());
    }
    if (this.dom.btnStarSnapTestShots) {
      this.dom.btnStarSnapTestShots.addEventListener("click", () => this.takeStarSnap());
    }
    if (this.dom.btnTakeSnapshotTestShots) {
      this.dom.btnTakeSnapshotTestShots.addEventListener("click", () => this.takeSnapshot());
    }
    if (this.dom.btnToggleLoupeTestShots) {
      this.dom.btnToggleLoupeTestShots.addEventListener("click", () => this.toggleLoupe());
    }

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

    // Quality Tier Switcher (Low, Balanced, Full)
    const tierButtons = document.querySelectorAll(".btn-segmented[data-tier]");
    tierButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        this.setImageTier(btn.dataset.tier);
      });
    });
    this.updateQualityTierButtons();

    // Execution Controls
    this.dom.btnStartTimelapse.addEventListener("click", () => this.startTimelapse());
    this.dom.btnPauseTimelapse.addEventListener("click", () => this.pauseOrResumeTimelapse());
    this.dom.btnStop.addEventListener("click", () => this.emergencyStop());
    this.dom.btnSavePlan.addEventListener("click", () => this.savePlan());
    if (this.dom.btnOpenPlan) {
      this.dom.btnOpenPlan.addEventListener("click", () => this.openLoadPlanDialog());
    }
    if (this.dom.btnRefreshPlansList) {
      this.dom.btnRefreshPlansList.addEventListener("click", () => this.fetchSavedPlans());
    }
    if (this.dom.openPlanModal) {
      this.dom.openPlanModal.addEventListener("click", (e) => {
        if (e.target === this.dom.openPlanModal) {
          this.closeOpenPlanModal();
        }
      });
    }

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
        this.detachFollowLiveIfRunning();
        if (e.shiftKey) this.goToPrevKey();
        else this.setPlayhead(this.playhead - 1);
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        this.detachFollowLiveIfRunning();
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

  async fetchInitialRigStatus() {
    try {
      const res = await fetch("/api/rig/status");
      if (res.ok) {
        const data = await res.json();
        if (data.reference) {
          this.handleLiveEvent({ reference: data.reference });
        }
      }
    } catch (e) {
      console.warn("Could not fetch initial rig status:", e);
    }

    try {
      const tlRes = await fetch("/api/timelapse/status");
      if (tlRes.ok) {
        const tlData = await tlRes.json();
        if (tlData) {
          this.handleLiveEvent({ timelapse: tlData });
        }
      }
    } catch (e) {
      console.warn("Could not fetch initial timelapse status:", e);
    }

    await this.fetchTimelapseCaptures();
    this.updateViewportForPlayhead();

    try {
      const camRes = await fetch("/api/camera/status");
      if (camRes.ok) {
        const camData = await camRes.json();
        if (camData.raw_enabled !== undefined && this.plan.defaults.raw === undefined) {
          this.plan.defaults.raw = Boolean(camData.raw_enabled);
          this.plan.defaults.image_format = camData.image_format || (camData.raw_enabled ? "RAW + L" : "L");
        }
        this.updateRawUI();
        if (camData.has_latest_photo && !this.isLiveViewActive && this.capturedShotsMap.size === 0) {
          // If no timelapse sequence is loaded or active, fallback to showing latest camera snapshot
          this.dom.previewImage.src = this.getPreviewUrl(true);
          this.dom.previewImage.style.display = "block";
          this.dom.viewportPlaceholder.style.display = "none";
          if (this.dom.latestPhotoPill) {
            this.dom.latestPhotoPill.style.display = "flex";
            this.dom.latestPhotoText.textContent = camData.latest_photo_filename || "Last Photo";
          }
        }
      }
    } catch (e) {
      console.warn("Could not fetch initial camera status:", e);
    }
  }

  async fetchTimelapseCaptures() {
    try {
      const res = await fetch("/api/timelapse/captures");
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          for (const item of data) {
            if (item && item.shot_index && item.filename) {
              this.capturedShotsMap.set(item.shot_index, item.filename);
            }
          }
        }
      }
    } catch (e) {
      console.warn("Could not fetch timelapse captures:", e);
    }
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
      const isZero = !!(data.reference.confirmed || data.reference.reference_confirmed);
      this.liveState.rig.reference_confirmed = isZero;
      this.liveState.rig.zero_state = isZero ? "OK" : "UNCONFIRMED";
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

      if (data.timelapse.current_shot > 0) {
        this.liveShot = data.timelapse.current_shot;
      }

      if (data.timelapse.latest_capture) {
        const lc = data.timelapse.latest_capture;
        if (lc.shot_index && lc.filename) {
          this.capturedShotsMap.set(lc.shot_index, lc.filename);
        }
      }

      if (tState === "RUNNING") {
        this.dom.btnStartTimelapse.style.display = "none";
        this.dom.btnPauseTimelapse.style.display = "inline-flex";
        this.dom.btnPauseTimelapse.textContent = "⏸ Pause";
        if (this.followLive && this.liveShot > 0) {
          this.setPlayhead(this.liveShot, false, true);
        } else {
          this.renderTimeline();
        }
      } else if (tState === "PAUSED") {
        this.dom.btnStartTimelapse.style.display = "none";
        this.dom.btnPauseTimelapse.style.display = "inline-flex";
        this.dom.btnPauseTimelapse.textContent = "▶ Resume";
        this.renderTimeline();
      } else {
        this.dom.btnStartTimelapse.style.display = "inline-flex";
        this.dom.btnPauseTimelapse.style.display = "none";
        this.followLive = true;
      }
      this.updateLiveTrackingUI();
    }
  }

  detachFollowLiveIfRunning() {
    const isTimelapseActive = this.liveState.timelapse.state === "RUNNING" || this.liveState.timelapse.state === "PAUSED";
    if (isTimelapseActive && this.followLive) {
      this.followLive = false;
      this.updateLiveTrackingUI();
      this.renderTimeline();
    }
  }

  toggleFollowLive() {
    this.followLive = !this.followLive;
    if (this.followLive && this.liveShot > 0) {
      this.setPlayhead(this.liveShot, true, true);
    }
    this.updateLiveTrackingUI();
    this.renderTimeline();
  }

  jumpToLive() {
    this.followLive = true;
    if (this.liveShot > 0) {
      this.setPlayhead(this.liveShot, true, true);
    }
    this.updateLiveTrackingUI();
    this.renderTimeline();
    this.showToast(`Snapped edit playhead to live execution at Shot ${this.liveShot}`, "info");
  }

  updateLiveTrackingUI() {
    const isTimelapseActive = this.liveState.timelapse.state === "RUNNING" || this.liveState.timelapse.state === "PAUSED";

    if (this.dom.followLiveToggleLabel) {
      this.dom.followLiveToggleLabel.style.display = isTimelapseActive ? "inline-flex" : "none";
      if (this.dom.chkFollowLive) {
        this.dom.chkFollowLive.checked = this.followLive;
      }
      if (this.followLive) {
        this.dom.followLiveToggleLabel.classList.add("active");
        if (this.dom.followLiveDot) this.dom.followLiveDot.className = "live-dot pulse";
        if (this.dom.followLiveLabel) this.dom.followLiveLabel.textContent = "Follow Live";
      } else {
        this.dom.followLiveToggleLabel.classList.remove("active");
        if (this.dom.followLiveDot) this.dom.followLiveDot.className = "live-dot";
        if (this.dom.followLiveLabel) this.dom.followLiveLabel.textContent = "Follow Live";
      }
    }

    if (this.dom.btnToggleFollowLive) {
      this.dom.btnToggleFollowLive.style.display = isTimelapseActive ? "inline-flex" : "none";
      if (this.followLive) {
        this.dom.btnToggleFollowLive.classList.add("active");
        if (this.dom.followLiveDot) this.dom.followLiveDot.className = "live-dot pulse";
        if (this.dom.followLiveLabel) this.dom.followLiveLabel.textContent = "Following Live";
      } else {
        this.dom.btnToggleFollowLive.classList.remove("active");
        if (this.dom.followLiveDot) this.dom.followLiveDot.className = "live-dot";
        if (this.dom.followLiveLabel) this.dom.followLiveLabel.textContent = "Follow: OFF";
      }
    }

    if (this.dom.detachedLivePill) {
      if (isTimelapseActive && !this.followLive && this.liveShot > 0) {
        this.dom.detachedLivePill.style.display = "flex";
        if (this.dom.detachedEditShot) this.dom.detachedEditShot.textContent = this.playhead;
        if (this.dom.detachedLiveShot) this.dom.detachedLiveShot.textContent = this.liveShot;
      } else {
        this.dom.detachedLivePill.style.display = "none";
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

    const isTimelapseActive = this.liveState.timelapse.state === "RUNNING" || this.liveState.timelapse.state === "PAUSED";
    const hasLiveProgress = this.liveShot > 0 && (isTimelapseActive || (this.liveState.timelapse.current_shot && this.liveState.timelapse.current_shot > 0));

    // 1. Shaded progress fill for completed shots behind execution needle
    if (hasLiveProgress) {
      const startX = this.shotToX(1);
      const liveX = this.shotToX(this.liveShot);
      if (liveX > startX) {
        ctx.fillStyle = "rgba(16, 185, 129, 0.08)";
        ctx.fillRect(startX, rulerH, liveX - startX, h - rulerH);
      }
    }

    // 2. Draw Live Execution Needle (Green #10b981) if active sequence
    if (hasLiveProgress) {
      const liveX = this.shotToX(this.liveShot);
      ctx.save();
      ctx.strokeStyle = "#10b981";
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(liveX, 0);
      ctx.lineTo(liveX, h);
      ctx.stroke();
      ctx.restore();

      // Live handle badge on ruler
      const badgeW = 30;
      const badgeH = 14;
      ctx.fillStyle = "#10b981";
      ctx.beginPath();
      if (ctx.roundRect) {
        ctx.roundRect(liveX - badgeW / 2, 2, badgeW, badgeH, 3);
      } else {
        ctx.rect(liveX - badgeW / 2, 2, badgeW, badgeH);
      }
      ctx.fill();

      ctx.save();
      ctx.fillStyle = "#0f172a";
      ctx.font = "bold 9px JetBrains Mono";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("LIVE", liveX, 9);
      ctx.restore();
    }

    // 3. Draw Edit Playhead (Red #ef4444, or Amber #f59e0b when detached)
    const isDetached = isTimelapseActive && !this.followLive;
    const playheadColor = isDetached ? "#f59e0b" : "#ef4444";
    const phX = this.shotToX(this.playhead);

    ctx.strokeStyle = playheadColor;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(phX, 0);
    ctx.lineTo(phX, h);
    ctx.stroke();

    // Playhead handle on ruler
    ctx.fillStyle = playheadColor;
    ctx.beginPath();
    ctx.moveTo(phX - 6, 0);
    ctx.lineTo(phX + 6, 0);
    ctx.lineTo(phX + 6, rulerH - 8);
    ctx.lineTo(phX, rulerH);
    ctx.lineTo(phX - 6, rulerH - 8);
    ctx.closePath();
    ctx.fill();

    if (isDetached) {
      ctx.save();
      ctx.fillStyle = "#0f172a";
      ctx.font = "bold 8px JetBrains Mono";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("EDIT", phX, 8);
      ctx.restore();
    }
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
    this.detachFollowLiveIfRunning();
    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const rulerH = 28;
    const rowH = 44;

    // In tracks view, activate track when clicked anywhere on its row
    if (this.viewMode === "tracks" && mouseY >= rulerH) {
      const activeTracks = Object.values(this.plan.tracks);
      const trackIdx = Math.floor((mouseY - rulerH) / rowH);
      if (trackIdx >= 0 && trackIdx < activeTracks.length) {
        this.activeTrackId = activeTracks[trackIdx].id;
      }
    }

    // Check click on keypoints across all tracks (in tracks view) or active track (in curve view)
    const tracksToCheck = this.viewMode === "tracks"
      ? Object.values(this.plan.tracks)
      : [this.plan.tracks[this.activeTrackId]].filter(Boolean);

    for (const tr of tracksToCheck) {
      for (const key of tr.keyframes) {
        const kx = this.shotToX(key.shotIndex);
        if (Math.abs(mouseX - kx) < 12) {
          this.activeTrackId = tr.id;
          this.selectedKeyId = key.id;
          this.dragTarget = { type: "key", trackId: tr.id, id: key.id };
          this.isDragging = true;
          this.setPlayhead(key.shotIndex, true, false);
          this.updateInspectorUI();
          this.renderTimeline();
          return;
        }
      }
    }

    // Otherwise scrub playhead
    const targetShot = this.xToShot(mouseX);
    this.dragTarget = { type: "playhead" };
    this.isDragging = true;
    this.setPlayhead(targetShot, true, false);
  }

  onCanvasMouseMove(e) {
    if (!this.isDragging || !this.dragTarget) return;

    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const targetShot = this.xToShot(mouseX);

    if (this.dragTarget.type === "playhead") {
      this.detachFollowLiveIfRunning();
      this.setPlayhead(targetShot, true, false);
    } else if (this.dragTarget.type === "key") {
      const track = this.plan.tracks[this.dragTarget.trackId];
      if (track) {
        const key = track.keyframes.find((k) => k.id === this.dragTarget.id);
        if (key) {
          key.shotIndex = Math.max(1, Math.min(this.plan.totalShots, targetShot));
          // If in curve mode on a continuous track, also drag angle vertically
          if (this.viewMode === "curve" && track.type === "continuous") {
            const rulerH = 28;
            const graphY = rulerH;
            const graphH = this.canvasHeight - rulerH;
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
            const fraction = (graphY + graphH - 20 - mouseY) / (graphH - 40);
            let rawVal = minVal + fraction * valRange;
            if (track.id === "tilt") rawVal = Math.max(-80, Math.min(80, rawVal));
            key.value = Number(rawVal.toFixed(1));
          }
          track.keyframes.sort((a, b) => a.shotIndex - b.shotIndex);
          this.setPlayhead(key.shotIndex, true, false);
          this.updateInspectorUI();
          this.renderTimeline();
          this.checkLiveRamping(track.id, key.value);
        }
      }
    }
  }

  onCanvasMouseUp() {
    const wasDragging = this.isDragging;
    this.isDragging = false;
    this.dragTarget = null;
    if (wasDragging) {
      this.updateViewportForPlayhead();
    }
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

    if (!this.plan.tracks[paramKey]) {
      const kfs = [];
      if (this.playhead === 1) {
        kfs.push({ id: `${paramKey}-start`, shotIndex: 1, value: initialVal || this.plan.defaults[paramKey] });
      } else {
        kfs.push({ id: `${paramKey}-start`, shotIndex: 1, value: this.plan.defaults[paramKey] });
        kfs.push({ id: `${paramKey}-${Date.now()}`, shotIndex: this.playhead, value: initialVal });
      }

      this.plan.tracks[paramKey] = {
        id: paramKey,
        label: labels[paramKey] || paramKey,
        color: colors[paramKey] || "#8b5cf6",
        type: "discrete",
        keyframes: kfs
      };
      this.activeTrackId = paramKey;
      this.selectedKeyId = kfs[kfs.length - 1].id;
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
      this.activeTrackId = paramKey;
      this.selectedKeyId = key.id;
    }
  }

  removeCameraTrack(paramKey) {
    const track = this.plan.tracks[paramKey];
    if (!track || track.type === "continuous") return;

    delete this.plan.tracks[paramKey];
    if (this.activeTrackId === paramKey) {
      this.activeTrackId = "pan";
      this.selectedKeyId = this.plan.tracks.pan.keyframes[0]?.id || null;
    }
    this.renderTrackHeaders();
    this.updateInspectorUI();
    this.renderTimeline();
    this.updateOverlays();
    this.showToast(`Removed track: ${track.label}`, "info");
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
        <div style="display: flex; align-items: center; gap: 6px;">
          <span style="color: ${track.color}; font-family: var(--font-mono); font-size: 11px;">${displayVal}</span>
          ${track.type === "discrete" ? `<button class="track-delete-btn" title="Remove track">✕</button>` : ""}
        </div>
      `;

      if (track.type === "discrete") {
        const delBtn = item.querySelector(".track-delete-btn");
        if (delBtn) {
          delBtn.onclick = (e) => {
            e.stopPropagation();
            this.removeCameraTrack(trackId);
          };
        }
      }

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
    this.detachFollowLiveIfRunning();
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
    this.detachFollowLiveIfRunning();
    const track = this.plan.tracks[this.activeTrackId];
    if (!track) return;
    const after = track.keyframes.filter((k) => k.shotIndex > this.playhead);
    if (after.length > 0) {
      const next = after[0];
      this.selectedKeyId = next.id;
      this.setPlayhead(next.shotIndex);
    }
  }

  addKeyTriggerAtPlayheadForTrack(trackId) {
    const track = this.plan.tracks[trackId];
    if (!track) return null;

    const existing = this.getKeyTriggerAtShot(track, this.playhead);
    if (existing) {
      this.selectedKeyId = existing.id;
      return existing;
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
    return newKey;
  }

  setKeyAngle(axis, val) {
    const track = this.plan.tracks[axis];
    if (!track) return;

    let key = this.getKeyTriggerAtShot(track, this.playhead);
    if (!key) {
      key = this.addKeyTriggerAtPlayheadForTrack(axis);
    }

    let num = parseFloat(val);
    if (isNaN(num)) num = 0.0;
    if (axis === "tilt") {
      num = Math.max(-80, Math.min(80, num));
    }

    if (key) {
      key.value = Number(num.toFixed(1));
    }

    this.updateInspectorUI();
    this.updateOverlays();
    this.renderTimeline();
    this.checkLiveRamping(axis, key ? key.value : num);
  }

  nudgeKeyAngle(axis, delta) {
    const track = this.plan.tracks[axis];
    if (!track) return;

    let key = this.getKeyTriggerAtShot(track, this.playhead);
    const curVal = key ? key.value : this.evaluateTrackAtShot(track, this.playhead);
    const newVal = Number((curVal + delta).toFixed(1));
    this.setKeyAngle(axis, newVal);
  }

  async moveRigToCurrentPose() {
    const pan = this.evaluateTrackAtShot(this.plan.tracks.pan, this.playhead);
    const tilt = this.evaluateTrackAtShot(this.plan.tracks.tilt, this.playhead);
    try {
      this.showToast(`Slewing rig to Pan ${Number(pan).toFixed(1)}°, Tilt ${Number(tilt).toFixed(1)}°...`, "info");
      const res = await fetch("/api/motors/move", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pan: Number(Number(pan).toFixed(1)), tilt: Number(Number(tilt).toFixed(1)), relative: false })
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail?.message || err.detail || "Move failed");
      }
      this.showToast(`Rig slewed to pose: Pan ${Number(pan).toFixed(1)}°, Tilt ${Number(tilt).toFixed(1)}°`, "success");
    } catch (e) {
      this.showToast(`Move error: ${e.message || e}`, "error");
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

    // Update Direct Pan & Tilt Angle Inputs (Software)
    const panKey = this.getKeyTriggerAtShot(this.plan.tracks.pan, this.playhead);
    const panVal = panKey ? panKey.value : this.evaluateTrackAtShot(this.plan.tracks.pan, this.playhead);
    if (this.dom.keyPanInput) {
      this.dom.keyPanInput.value = Number(panVal).toFixed(1);
    }
    if (this.dom.panKeyIndicator) {
      this.dom.panKeyIndicator.textContent = panKey ? "Key" : "Interpolated";
      this.dom.panKeyIndicator.style.color = panKey ? "#06b6d4" : "var(--text-dim)";
    }

    const tiltKey = this.getKeyTriggerAtShot(this.plan.tracks.tilt, this.playhead);
    const tiltVal = tiltKey ? tiltKey.value : this.evaluateTrackAtShot(this.plan.tracks.tilt, this.playhead);
    if (this.dom.keyTiltInput) {
      this.dom.keyTiltInput.value = Number(tiltVal).toFixed(1);
    }
    if (this.dom.tiltKeyIndicator) {
      this.dom.tiltKeyIndicator.textContent = tiltKey ? "Key" : "Interpolated";
      this.dom.tiltKeyIndicator.style.color = tiltKey ? "#f97316" : "var(--text-dim)";
    }

    if (track.type === "continuous") {
      if (this.dom.parameterValueContainer) this.dom.parameterValueContainer.style.display = "none";
      if (this.dom.easingContainer) this.dom.easingContainer.style.display = "block";
      if (this.dom.keyEasingSelect) this.dom.keyEasingSelect.value = key?.mode || "auto";
    } else {
      if (this.dom.parameterValueContainer) this.dom.parameterValueContainer.style.display = "block";
      if (this.dom.easingContainer) this.dom.easingContainer.style.display = "none";
      if (this.dom.lblParameterValue) this.dom.lblParameterValue.textContent = `Target ${track.label} (Hold Step)`;

      const choices = this.cameraChoices[track.id] || [];
      if (this.dom.keyDiscreteSelect) {
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

    // Synchronize Section 3 controls with evaluated values at active playhead
    const curIso = this.evaluateTrackAtShot(this.plan.tracks.iso || { id: "iso" }, this.playhead);
    const curShutter = this.evaluateTrackAtShot(this.plan.tracks.shutter_speed || { id: "shutter_speed" }, this.playhead);
    const curAperture = this.evaluateTrackAtShot(this.plan.tracks.aperture || { id: "aperture" }, this.playhead);
    const curWb = this.evaluateTrackAtShot(this.plan.tracks.white_balance || { id: "white_balance" }, this.playhead);

    if (this.dom.defaultIsoSelect && curIso) this.dom.defaultIsoSelect.value = curIso;
    if (this.dom.defaultShutterSelect && curShutter) this.dom.defaultShutterSelect.value = curShutter;
    if (this.dom.defaultApertureSelect && curAperture) this.dom.defaultApertureSelect.value = curAperture;
    if (this.dom.defaultWbSelect && curWb) this.dom.defaultWbSelect.value = curWb;

    if (this.dom.cameraTrackContextBadge) {
      if (this.playhead === 1) {
        this.dom.cameraTrackContextBadge.textContent = "Shot 1 (Default)";
        this.dom.cameraTrackContextBadge.style.background = "rgba(59, 130, 246, 0.15)";
        this.dom.cameraTrackContextBadge.style.color = "#93c5fd";
        this.dom.cameraTrackContextBadge.style.borderColor = "rgba(59, 130, 246, 0.3)";
      } else {
        this.dom.cameraTrackContextBadge.textContent = `Shot ${this.playhead} (Active)`;
        this.dom.cameraTrackContextBadge.style.background = "rgba(16, 185, 129, 0.15)";
        this.dom.cameraTrackContextBadge.style.color = "#6ee7b7";
        this.dom.cameraTrackContextBadge.style.borderColor = "rgba(16, 185, 129, 0.3)";
      }
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

  setPlayhead(shotIndex, updateInput = true, loadMedia = true) {
    this.playhead = Math.max(1, Math.min(this.plan.totalShots, shotIndex));
    if (updateInput) this.dom.playheadInput.value = this.playhead;

    const track = this.plan.tracks[this.activeTrackId];
    if (track) {
      const key = this.getKeyTriggerAtShot(track, this.playhead);
      if (key) this.selectedKeyId = key.id;
    }

    this.updateInspectorUI();
    this.updateOverlays();
    this.updateLiveTrackingUI();
    this.renderTimeline();

    if (loadMedia && !this.isDragging && !this.isPlayingPreview) {
      this.updateViewportForPlayhead();
    }
  }

  updateViewportForPlayhead() {
    // Only manage timelapse viewport when on timelapse tab and not streaming live view
    if (this.activeViewportTab !== "timelapse" || this.isLiveViewActive) return;

    if (this.capturedShotsMap && this.capturedShotsMap.has(this.playhead)) {
      const fn = this.capturedShotsMap.get(this.playhead);
      const imgUrl = `/api/timelapse/captures/${encodeURIComponent(fn)}?quality=${this.imageTier}`;
      this.dom.previewImage.src = imgUrl;
      this.dom.previewImage.style.display = "block";
      this.dom.viewportPlaceholder.style.display = "none";
      if (this.dom.latestPhotoPill) {
        this.dom.latestPhotoPill.style.display = "flex";
        this.dom.latestPhotoText.textContent = `Shot ${this.playhead}: ${fn}`;
      }
    } else {
      // Uncaptured / future frame: hide image and display clean frame placeholder
      this.dom.previewImage.style.display = "none";
      this.dom.viewportPlaceholder.style.display = "flex";
      if (this.dom.viewportPlaceholderText) {
        this.dom.viewportPlaceholderText.textContent =
          `Shot ${this.playhead} / ${this.plan.totalShots} • Uncaptured • Adjust settings to add key trigger`;
      }
      if (this.dom.latestPhotoPill) {
        this.dom.latestPhotoPill.style.display = "none";
      }
    }
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
    if (this.dom.btnToggleLoupe) this.dom.btnToggleLoupe.classList.toggle("btn-primary", this.isLoupeActive);
    if (this.dom.btnToggleLoupeTestShots) this.dom.btnToggleLoupeTestShots.classList.toggle("btn-primary", this.isLoupeActive);
    this.dom.viewportContainer.classList.toggle("loupe-active", this.isLoupeActive);
    if (!this.isLoupeActive && this.dom.loupeOverlay) {
      this.dom.loupeOverlay.style.display = "none";
    }
    if (this.isLoupeActive) {
      const tip = this.imageTier !== "full" ? " (Tip: select 'Full' tier for pin-sharp star inspection)" : "";
      this.showToast(`5x Loupe ON: Hover over viewport to inspect star focus${tip}`);
    } else {
      this.showToast("5x Loupe OFF");
    }
  }

  /* -------------------------------------------------------------------------- */
  /* Viewport Mode Tabbing & Test Shots History                                 */
  /* -------------------------------------------------------------------------- */
  switchViewportTab(tabName) {
    if (tabName !== "timelapse" && tabName !== "test-shots") return;
    this.activeViewportTab = tabName;

    const isTimelapse = tabName === "timelapse";

    if (this.dom.tabBtnTimelapse) this.dom.tabBtnTimelapse.classList.toggle("active", isTimelapse);
    if (this.dom.tabBtnTestShots) this.dom.tabBtnTestShots.classList.toggle("active", !isTimelapse);

    if (this.dom.timelapseControlsWrapper) {
      this.dom.timelapseControlsWrapper.style.display = isTimelapse ? "block" : "none";
    }
    if (this.dom.testShotsControlsWrapper) {
      this.dom.testShotsControlsWrapper.style.display = isTimelapse ? "none" : "block";
    }
    if (this.dom.testShotsHeaderActions) {
      this.dom.testShotsHeaderActions.style.display = isTimelapse ? "none" : "flex";
    }

    if (isTimelapse) {
      // Restore timelapse viewport state
      if (this.dom.testShotMetaPill) this.dom.testShotMetaPill.style.display = "none";
      if (this.dom.shotCounterOverlay) this.dom.shotCounterOverlay.style.display = "block";
      if (this.dom.timingOverlay) this.dom.timingOverlay.style.display = "block";
      if (this.dom.interpolatedPoseOverlay) this.dom.interpolatedPoseOverlay.style.display = "block";
      if (this.isLiveViewActive) {
        this.dom.previewImage.src = `/api/camera/preview/stream?t=${Date.now()}`;
        this.dom.previewImage.style.display = "block";
        this.dom.viewportPlaceholder.style.display = "none";
      } else {
        this.updateViewportForPlayhead();
      }
    } else {
      // Switch to Test Shots mode
      if (this.isLiveViewActive) {
        this.toggleLiveView(); // Stop live view stream when entering history
      }
      if (this.dom.shotCounterOverlay) this.dom.shotCounterOverlay.style.display = "none";
      if (this.dom.timingOverlay) this.dom.timingOverlay.style.display = "none";
      if (this.dom.interpolatedPoseOverlay) this.dom.interpolatedPoseOverlay.style.display = "none";
      if (this.dom.latestPhotoPill) this.dom.latestPhotoPill.style.display = "none";

      this.fetchTestShots(true);
    }
  }

  async fetchTestShots(autoSelect = false) {
    try {
      const res = await fetch("/api/camera/test-shots");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      this.testShots = data.test_shots || [];

      if (this.dom.testShotsCountBadge) {
        this.dom.testShotsCountBadge.textContent = this.testShots.length;
      }

      this.renderTestShotsFilmstrip();

      if (autoSelect || !this.selectedTestShot) {
        if (this.testShots.length > 0) {
          this.selectTestShot(this.testShots[0].filename);
        } else {
          this.selectedTestShot = null;
          if (this.dom.selectedShotLabel) this.dom.selectedShotLabel.textContent = "No test shots found";
          if (this.dom.testShotMetaPill) this.dom.testShotMetaPill.style.display = "none";
          if (this.activeViewportTab === "test-shots") {
            this.dom.previewImage.style.display = "none";
            this.dom.viewportPlaceholder.style.display = "flex";
            if (this.dom.viewportPlaceholderText) {
              this.dom.viewportPlaceholderText.textContent = "No test shots recorded yet. Take a Star Snap or Snapshot.";
            }
          }
        }
      }
    } catch (e) {
      console.warn("Could not fetch test shots:", e);
      if (this.dom.testShotsFilmstrip) {
        this.dom.testShotsFilmstrip.innerHTML = `<div class="test-shots-empty">Could not load test shots: ${e.message || e}</div>`;
      }
    }
  }

  renderTestShotsFilmstrip() {
    const container = this.dom.testShotsFilmstrip;
    if (!container) return;

    if (!this.testShots || this.testShots.length === 0) {
      container.innerHTML = `<div class="test-shots-empty">No test shots recorded yet. Capture a Star Snap or Snapshot above.</div>`;
      return;
    }

    container.innerHTML = "";
    this.testShots.forEach((shot) => {
      const card = document.createElement("div");
      card.className = `test-shot-card ${shot.filename === this.selectedTestShot ? "active" : ""}`;
      card.title = `Click to inspect ${shot.filename} (${shot.size_human})`;

      // Low tier URL for thumbnail
      const thumbUrl = `/api/camera/test-shots/${shot.filename}?quality=low`;

      card.innerHTML = `
        <div class="test-shot-thumb-wrap">
          <img class="test-shot-thumb" src="${thumbUrl}" alt="${shot.filename}" loading="lazy" onerror="this.style.opacity='0.2'">
        </div>
        <div class="test-shot-info">
          <div class="test-shot-time">${shot.time_display || shot.filename}</div>
          <div class="test-shot-meta">
            <span>${shot.date_display || ""}</span>
            <span>${shot.size_human}</span>
          </div>
        </div>
      `;

      card.addEventListener("click", () => {
        this.selectTestShot(shot.filename);
      });

      container.appendChild(card);
    });
  }

  selectTestShot(filename) {
    if (!filename) return;
    this.selectedTestShot = filename;
    const shot = this.testShots ? this.testShots.find((s) => s.filename === filename) : null;

    // Highlight active card in filmstrip
    if (this.dom.testShotsFilmstrip) {
      const cards = this.dom.testShotsFilmstrip.querySelectorAll(".test-shot-card");
      cards.forEach((c, idx) => {
        const s = this.testShots ? this.testShots[idx] : null;
        c.classList.toggle("active", s && s.filename === filename);
      });
    }

    // Update label & pill
    if (this.dom.selectedShotLabel) {
      this.dom.selectedShotLabel.textContent = shot ? `${shot.filename} (${shot.size_human})` : filename;
    }
    if (this.dom.testShotMetaPill) {
      this.dom.testShotMetaPill.style.display = "flex";
      this.dom.testShotMetaText.textContent = shot
        ? `Test Shot: ${shot.time_display || ""} • ${shot.size_human}`
        : `Test Shot: ${filename}`;
    }

    // Load photo in viewport
    const imgUrl = `/api/camera/test-shots/${filename}?quality=${this.imageTier}&t=${Date.now()}`;
    this.dom.previewImage.src = imgUrl;
    this.dom.previewImage.style.display = "block";
    this.dom.viewportPlaceholder.style.display = "none";
  }

  async deleteSelectedTestShot() {
    if (!this.selectedTestShot) {
      this.showToast("No test shot selected to delete", "warning");
      return;
    }

    const filename = this.selectedTestShot;
    if (!confirm(`Delete test shot '${filename}'? This cannot be undone.`)) {
      return;
    }

    try {
      const res = await fetch(`/api/camera/test-shots/${filename}`, { method: "DELETE" });
      const data = await res.json();
      if (data.status === "OK") {
        this.showToast(`Deleted ${filename}`, "success");
        this.selectedTestShot = null;
        await this.fetchTestShots(true);
      } else {
        this.showToast(`Delete failed: ${data.message || "Unknown error"}`, "error");
      }
    } catch (e) {
      this.showToast(`Delete error: ${e}`, "error");
    }
  }

  async deleteAllTestShots() {
    if (!this.testShots || this.testShots.length === 0) {
      this.showToast("No test shots to delete", "info");
      return;
    }

    const count = this.testShots.length;
    if (!confirm(`Are you sure you want to delete ALL ${count} test shots? This cannot be undone.`)) {
      return;
    }

    try {
      const res = await fetch("/api/camera/test-shots", { method: "DELETE" });
      const data = await res.json();
      if (res.ok && data.status === "OK") {
        this.showToast(`Deleted all ${data.count} test shots`, "success");
        this.selectedTestShot = null;
        this.testShots = [];
        await this.fetchTestShots(false);
        this.updatePreviewImage();
      } else {
        this.showToast(`Delete all failed: ${data.detail || data.message || "Unknown error"}`, "error");
      }
    } catch (e) {
      this.showToast(`Delete all error: ${e.message || e}`, "error");
    }
  }

  updateQualityTierButtons() {
    document.querySelectorAll(".btn-segmented[data-tier]").forEach((b) => {
      b.classList.toggle("active", b.dataset.tier === this.imageTier);
    });
  }

  setImageTier(tier) {
    if (!["low", "balanced", "full"].includes(tier)) return;
    this.imageTier = tier;
    localStorage.setItem("pantiltlapse_image_quality", tier);
    this.updateQualityTierButtons();

    const tierLabels = {
      low: "Low (1024px, fastest over Wi-Fi)",
      balanced: "Balanced (1080p, crisp framing)",
      full: "Full Native Sensor Resolution (best for Loupe)",
    };

    this.showToast(`Preview quality: ${tierLabels[tier]}`);

    // If an image is currently visible in the viewport and not streaming, reload it in the requested tier
    if (!this.isLiveViewActive && this.dom.previewImage && this.dom.previewImage.style.display !== "none") {
      this.reloadPreviewImage();
    }
  }

  getPreviewUrl(bustCache = false) {
    if (this.activeViewportTab === "test-shots" && this.selectedTestShot) {
      const base = `/api/camera/test-shots/${this.selectedTestShot}?quality=${this.imageTier}`;
      return bustCache ? `${base}&t=${Date.now()}` : base;
    }
    if (this.activeViewportTab === "timelapse" && this.capturedShotsMap && this.capturedShotsMap.has(this.playhead)) {
      const fn = this.capturedShotsMap.get(this.playhead);
      const base = `/api/timelapse/captures/${encodeURIComponent(fn)}?quality=${this.imageTier}`;
      return bustCache ? `${base}&t=${Date.now()}` : base;
    }
    const base = `/api/camera/preview/latest?quality=${this.imageTier}`;
    return bustCache ? `${base}&t=${Date.now()}` : base;
  }

  reloadPreviewImage() {
    if (!this.dom.previewImage || this.isLiveViewActive) return;
    if (this.imageTier === "full") {
      this.showToast("Loading full-resolution image from camera...");
    }
    this.dom.previewImage.src = this.getPreviewUrl(true);
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

  parseShutterSeconds(shutterStr) {
    if (!shutterStr) return 1.0;
    const s = String(shutterStr).trim().toLowerCase();
    if (s === "bulb") return 30.0;
    if (s.includes("/")) {
      const parts = s.split("/");
      const num = parseFloat(parts[0]);
      const den = parseFloat(parts[1]);
      if (den && den > 0) return num / den;
    }
    const val = parseFloat(s);
    return isNaN(val) || val <= 0 ? 1.0 : val;
  }

  async triggerExposureWithCountdown({
    iso = null,
    shutter = null,
    aperture = null,
    whiteBalance = null,
    label = "Snapshot",
    restoreAfter = false
  } = {}) {
    // Determine active target settings from requested parameters or UI defaults
    const activeIso = String(iso || this.dom.defaultIsoSelect?.value || this.plan.defaults.iso || "100");
    const activeShutter = String(shutter || this.dom.defaultShutterSelect?.value || this.plan.defaults.shutter_speed || "1/250");
    const expSeconds = Math.max(0.1, this.parseShutterSeconds(activeShutter));

    // Disable snapshot trigger buttons during exposure
    if (this.dom.btnTakeSnapshot) this.dom.btnTakeSnapshot.disabled = true;
    if (this.dom.btnStarSnap) this.dom.btnStarSnap.disabled = true;
    if (this.dom.btnTakeSnapshotTestShots) this.dom.btnTakeSnapshotTestShots.disabled = true;
    if (this.dom.btnStarSnapTestShots) this.dom.btnStarSnapTestShots.disabled = true;

    // Show exposure countdown overlay
    const overlay = this.dom.exposureCountdownOverlay;
    const title = this.dom.exposureTitle;
    const timer = this.dom.exposureTimer;
    const fill = this.dom.exposureProgressFill;
    const details = this.dom.exposureDetails;

    if (overlay) {
      overlay.style.display = "flex";
      title.textContent = `📸 Exposing ${label}...`;
      details.textContent = `ISO ${activeIso} • ${activeShutter}s${this.liveState.camera?.aperture ? ' • f/' + this.liveState.camera.aperture : ''}`;
      fill.style.width = "0%";
      timer.textContent = `0.0s / ${expSeconds.toFixed(1)}s`;
    }

    let startTime = Date.now();
    const countdownInterval = setInterval(() => {
      const elapsed = (Date.now() - startTime) / 1000;
      if (elapsed <= expSeconds) {
        const pct = Math.min(100, (elapsed / expSeconds) * 100);
        if (fill) fill.style.width = `${pct.toFixed(1)}%`;
        if (timer) timer.textContent = `${elapsed.toFixed(1)}s / ${expSeconds.toFixed(1)}s`;
      } else {
        if (fill) fill.style.width = "100%";
        if (title) title.textContent = `📥 Transferring photo from camera...`;
        const transferSec = (elapsed - expSeconds).toFixed(1);
        if (timer) timer.textContent = `Shutter closed (${expSeconds.toFixed(1)}s) • Downloading +${transferSec}s`;
      }
    }, 100);

    const cleanup = () => {
      clearInterval(countdownInterval);
      if (overlay) overlay.style.display = "none";
      if (this.dom.btnTakeSnapshot) this.dom.btnTakeSnapshot.disabled = false;
      if (this.dom.btnStarSnap) this.dom.btnStarSnap.disabled = false;
      if (this.dom.btnTakeSnapshotTestShots) this.dom.btnTakeSnapshotTestShots.disabled = false;
      if (this.dom.btnStarSnapTestShots) this.dom.btnStarSnapTestShots.disabled = false;
    };

    try {
      let prevIso = null;
      let prevShutter = null;

      // Check if camera settings need to be updated before exposure
      const needsIsoChange = activeIso && String(activeIso) !== String(this.liveState.camera?.iso);
      const needsShutterChange = activeShutter && String(activeShutter) !== String(this.liveState.camera?.shutter_speed);
      const needsApertureChange = aperture && String(aperture) !== String(this.liveState.camera?.aperture);
      const needsWbChange = whiteBalance && String(whiteBalance) !== String(this.liveState.camera?.white_balance);

      if (needsIsoChange || needsShutterChange || needsApertureChange || needsWbChange) {
        prevIso = this.liveState.camera?.iso;
        prevShutter = this.liveState.camera?.shutter_speed;
        if (title) title.textContent = `⚙ Setting Camera (${activeShutter}s, ISO ${activeIso})...`;

        const configBody = {};
        if (needsIsoChange) configBody.iso = String(activeIso);
        if (needsShutterChange) configBody.shutter_speed = String(activeShutter);
        if (needsApertureChange) configBody.aperture = String(aperture);
        if (needsWbChange) configBody.white_balance = String(whiteBalance);

        try {
          const confRes = await fetch("/api/camera/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(configBody)
          });
          if (!confRes.ok) {
            console.warn("Camera config change rejected:", await confRes.text());
          } else {
            if (this.liveState.camera) {
              if (needsIsoChange) this.liveState.camera.iso = String(activeIso);
              if (needsShutterChange) this.liveState.camera.shutter_speed = String(activeShutter);
              if (needsApertureChange) this.liveState.camera.aperture = String(aperture);
              if (needsWbChange) this.liveState.camera.white_balance = String(whiteBalance);
            }
          }
        } catch (confErr) {
          console.warn("Could not apply camera config:", confErr);
        }
      }

      if (title) title.textContent = `📸 Exposing ${label}...`;
      startTime = Date.now();

      // Trigger actual camera shutter
      const res = await fetch("/api/camera/trigger", { method: "POST" });
      const data = await res.json();

      // Restore camera settings ONLY if restoreAfter was requested (e.g. Star Snap transient test)
      if (restoreAfter && (prevIso || prevShutter)) {
        try {
          const restoreBody = {};
          if (prevIso && prevIso !== activeIso) restoreBody.iso = String(prevIso);
          if (prevShutter && prevShutter !== activeShutter) restoreBody.shutter_speed = String(prevShutter);
          if (Object.keys(restoreBody).length > 0) {
            await fetch("/api/camera/config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(restoreBody)
            });
            if (this.liveState.camera) {
              if (prevIso) this.liveState.camera.iso = String(prevIso);
              if (prevShutter) this.liveState.camera.shutter_speed = String(prevShutter);
            }
          }
        } catch (_) {}
      }

      if (data.status === "OK") {
        const capturedFile = data.filename || data.camera_filename;
        if (capturedFile) {
          this.selectedTestShot = capturedFile;
        }

        if (title) title.textContent = "📥 Loading photo preview...";
        await this.fetchTestShots(false);

        const nowStr = new Date().toLocaleTimeString();
        if (this.dom.latestPhotoPill) {
          this.dom.latestPhotoPill.style.display = "flex";
          this.dom.latestPhotoText.textContent = `${label} (${activeIso}, ${activeShutter}s) @ ${nowStr}`;
        }

        if (this.activeViewportTab === "test-shots" && capturedFile) {
          this.selectTestShot(capturedFile);
          cleanup();
          this.showToast(`${label} captured (${activeIso}, ${activeShutter}s)!`, "success");
        } else {
          const imgUrl = this.getPreviewUrl(true);
          const tempImg = new Image();

          let finished = false;
          const renderPhoto = () => {
            if (finished) return;
            finished = true;
            cleanup();
            this.dom.previewImage.src = imgUrl;
            this.dom.previewImage.style.display = "block";
            this.dom.viewportPlaceholder.style.display = "none";
            this.showToast(`${label} captured (${activeIso}, ${activeShutter}s)!`, "success");
          };

          const loadTimeout = setTimeout(() => {
            renderPhoto();
          }, 3500);

          tempImg.onload = () => {
            clearTimeout(loadTimeout);
            renderPhoto();
          };

          tempImg.onerror = () => {
            clearTimeout(loadTimeout);
            if (finished) return;
            finished = true;
            cleanup();
            this.showToast(`${label} captured, but preview failed to load`, "warning");
          };

          tempImg.src = imgUrl;
        }
      } else {
        cleanup();
        this.showToast(`${label} failed: ${data.message || "Unknown error"}`, "error");
      }
    } catch (e) {
      cleanup();
      this.showToast(`${label} error: ${e}`, "error");
    }
  }

  async takeStarSnap() {
    let starIso = "12800";
    if (this.cameraChoices.iso?.length && !this.cameraChoices.iso.includes("12800")) {
      starIso = this.cameraChoices.iso.includes("6400")
        ? "6400"
        : (this.cameraChoices.iso.includes("3200") ? "3200" : this.cameraChoices.iso[this.cameraChoices.iso.length - 1]);
    }
    let starShutter = "2.5";
    if (this.cameraChoices.shutter_speed?.length && !this.cameraChoices.shutter_speed.includes("2.5")) {
      starShutter = this.cameraChoices.shutter_speed.includes("2")
        ? "2"
        : (this.cameraChoices.shutter_speed.includes("1") ? "1" : "1/2");
    }

    await this.triggerExposureWithCountdown({
      iso: starIso,
      shutter: starShutter,
      label: "Star Snap",
      restoreAfter: true
    });
  }

  async takeSnapshot() {
    // Determine target settings from the current playhead pose/parameters (or sequence defaults)
    const targetShutter = (this.plan.tracks.shutter_speed ? this.evaluateTrackAtShot(this.plan.tracks.shutter_speed, this.playhead) : null)
      || this.dom.defaultShutterSelect?.value
      || this.plan.defaults.shutter_speed
      || "1/250";

    const targetIso = (this.plan.tracks.iso ? this.evaluateTrackAtShot(this.plan.tracks.iso, this.playhead) : null)
      || this.dom.defaultIsoSelect?.value
      || this.plan.defaults.iso
      || "100";

    const targetAperture = (this.plan.tracks.aperture ? this.evaluateTrackAtShot(this.plan.tracks.aperture, this.playhead) : null)
      || this.dom.defaultApertureSelect?.value
      || this.plan.defaults.aperture;

    const targetWb = (this.plan.tracks.white_balance ? this.evaluateTrackAtShot(this.plan.tracks.white_balance, this.playhead) : null)
      || this.dom.defaultWbSelect?.value
      || this.plan.defaults.white_balance;

    await this.triggerExposureWithCountdown({
      iso: String(targetIso),
      shutter: String(targetShutter),
      aperture: targetAperture ? String(targetAperture) : null,
      whiteBalance: targetWb ? String(targetWb) : null,
      label: "Snapshot",
      restoreAfter: false
    });
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
      this.updateViewportForPlayhead();
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
        if (data.raw_enabled !== undefined) {
          this.plan.defaults.raw = Boolean(data.raw_enabled);
          this.plan.defaults.image_format = data.image_format || (data.raw_enabled ? "RAW + L" : "L");
        }
        this.populateSelectOptions();
        this.updateRawUI();
        this.updateOverlays();
        this.showToast("Synced camera settings as defaults", "success");
      }
    } catch (e) {
      this.showToast(`Camera sync error: ${e}`, "error");
    }
  }

  async setRawCapture(isRaw) {
    this.plan.defaults.raw = Boolean(isRaw);
    this.plan.defaults.image_format = isRaw ? "RAW + L" : "L";
    this.updateRawUI();

    if (this.liveState.timelapse.state !== "RUNNING") {
      try {
        await fetch("/api/camera/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ raw: isRaw })
        });
        if (this.liveState.camera) {
          this.liveState.camera.raw_enabled = isRaw;
          this.liveState.camera.image_format = isRaw ? "RAW + L" : "L";
        }
        this.showToast(isRaw ? "RAW capture enabled (RAW + JPEG)" : "RAW capture disabled (JPEG only)", "info");
      } catch (err) {
        console.warn("Could not push RAW config to camera:", err);
      }
    }
  }

  updateRawUI() {
    const isRaw = Boolean(this.plan.defaults?.raw);
    if (this.dom.chkCaptureRaw) {
      this.dom.chkCaptureRaw.checked = isRaw;
    }
    if (this.dom.rawFormatBadge) {
      if (isRaw) {
        this.dom.rawFormatBadge.textContent = "RAW + JPEG";
        this.dom.rawFormatBadge.className = "badge badge-primary";
      } else {
        this.dom.rawFormatBadge.textContent = "JPEG Only";
        this.dom.rawFormatBadge.className = "badge";
      }
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

    if (this.playhead >= this.plan.totalShots) this.setPlayhead(1, true, false);

    this.previewIntervalId = setInterval(() => {
      if (this.playhead < this.plan.totalShots) {
        this.setPlayhead(this.playhead + 1, true, false);
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
    this.updateViewportForPlayhead();
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
      raw: Boolean(this.plan.defaults?.raw),
      image_format: this.plan.defaults?.image_format || (this.plan.defaults?.raw ? "RAW + L" : "L"),
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
      if (data.status === "OK") {
        this.capturedShotsMap.clear();
        this.followLive = true;
        this.liveShot = 1;
        this.setPlayhead(1, true, true);
        this.updateLiveTrackingUI();
        this.showToast("Time-lapse sequence started!", "success");
      } else {
        this.showToast(`Start failed: ${data.message}`, "error");
      }
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

  /* -------------------------------------------------------------------------- */
  /* Plan Persistence & Open / Load Session Workflow                            */
  /* -------------------------------------------------------------------------- */
  serializeCurrentPlan() {
    const total = Math.max(2, parseInt(this.plan.totalShots) || 240);
    const interval = Math.max(1.0, parseFloat(this.plan.interval_s) || 5.0);
    const settle = Math.max(0.0, parseFloat(this.plan.settle_time_s) || 0.5);

    // Pan Axis Keyframes
    const panTrack = this.plan.tracks.pan || { keyframes: [] };
    const panKfs = (panTrack.keyframes || []).map((k) => ({ ...k }));
    panKfs.sort((a, b) => a.shotIndex - b.shotIndex);

    if (panKfs.length === 0) {
      panKfs.push({ id: "p1", shotIndex: 1, value: 0.0, mode: "smooth" });
      panKfs.push({ id: "p2", shotIndex: total, value: 0.0, mode: "smooth" });
    } else if (panKfs.length === 1) {
      panKfs.push({ id: "p2", shotIndex: total, value: panKfs[0].value, mode: "smooth" });
    }

    // Tilt Axis Keyframes
    const tiltTrack = this.plan.tracks.tilt || { keyframes: [] };
    const tiltKfs = (tiltTrack.keyframes || []).map((k) => ({ ...k }));
    tiltKfs.sort((a, b) => a.shotIndex - b.shotIndex);

    if (tiltKfs.length === 0) {
      tiltKfs.push({ id: "t1", shotIndex: 1, value: 0.0, mode: "smooth" });
      tiltKfs.push({ id: "t2", shotIndex: total, value: 0.0, mode: "smooth" });
    } else if (tiltKfs.length === 1) {
      tiltKfs.push({ id: "t2", shotIndex: total, value: tiltKfs[0].value, mode: "smooth" });
    }

    const formatKeyframes = (kfs) => {
      const n = kfs.length;
      const formatted = kfs.map((kf, i) => {
        let progress = 0.0;
        if (i === 0) {
          progress = 0.0;
        } else if (i === n - 1) {
          progress = 1.0;
        } else {
          progress = Math.max(0.0001, Math.min(0.9999, (kf.shotIndex - 1) / (total - 1)));
        }
        return {
          progress,
          value: Number(kf.value) || 0.0,
          outgoing_mode: kf.mode === "linear" ? "linear" : "smooth",
          tangent_scale: 1.0
        };
      });

      // Enforce strictly increasing progress
      for (let i = 1; i < formatted.length; i++) {
        if (formatted[i].progress <= formatted[i - 1].progress) {
          formatted[i].progress = Math.min(1.0, formatted[i - 1].progress + 0.001);
        }
      }
      formatted[0].progress = 0.0;
      formatted[formatted.length - 1].progress = 1.0;
      return formatted;
    };

    const payload = {
      name: (this.dom.planNameInput.value.trim() || this.plan.name || "Timeline Plan"),
      description: "Saved from Pantiltlapse Web Studio",
      schedule: {
        total_shots: total,
        interval_s: interval,
        settle_time_s: settle
      },
      trajectory: {
        pan_keyframes: formatKeyframes(panKfs),
        tilt_keyframes: formatKeyframes(tiltKfs)
      },
      acquisition: {
        iso: String(this.plan.defaults.iso || "100"),
        shutter_speed: String(this.plan.defaults.shutter_speed || "1/250"),
        aperture: String(this.plan.defaults.aperture || "4.0"),
        white_balance: String(this.plan.defaults.white_balance || "Auto"),
        camera_format: this.plan.defaults?.raw ? "RAW+JPEG" : "JPEG",
        extra_settings: {
          raw: Boolean(this.plan.defaults?.raw),
          image_format: this.plan.defaults?.image_format || (this.plan.defaults?.raw ? "RAW + L" : "L"),
          studio_plan: JSON.parse(JSON.stringify(this.plan))
        }
      }
    };

    if (this.currentPlanId) {
      payload.id = this.currentPlanId;
      payload.revision = this.currentPlanRevision || 1;
    }

    return payload;
  }

  async savePlan() {
    const planName = this.dom.planNameInput.value.trim() || this.plan.name || "Timeline Plan";
    this.plan.name = planName;

    // Cache locally immediately
    localStorage.setItem("pantiltlapse_saved_plan", JSON.stringify(this.plan));

    try {
      const payload = this.serializeCurrentPlan();
      let res;
      if (this.currentPlanId) {
        payload.id = this.currentPlanId;
        payload.revision = this.currentPlanRevision || 1;
        res = await fetch(`/api/plans/${this.currentPlanId}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (res.status === 404 || res.status === 409) {
          delete payload.id;
          delete payload.revision;
          res = await fetch("/api/plans", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
        }
      } else {
        res = await fetch("/api/plans", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
      }

      if (res.ok) {
        const saved = await res.json();
        this.currentPlanId = saved.id;
        this.currentPlanRevision = saved.revision;
        fetch("/api/app/state", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ active_plan_id: this.currentPlanId })
        }).catch(() => {});
        this.showToast(`Plan "${planName}" saved to rig storage`, "success");
      } else {
        const err = await res.json().catch(() => ({}));
        this.showToast(`Plan saved locally, server: ${err.detail?.message || res.statusText}`, "warning");
      }
    } catch (e) {
      this.showToast(`Plan "${planName}" saved locally (offline)`, "info");
    }
  }

  openLoadPlanDialog() {
    if (this.dom.openPlanModal) {
      this.dom.openPlanModal.style.display = "flex";
      this.fetchSavedPlans();
    }
  }

  closeOpenPlanModal() {
    if (this.dom.openPlanModal) {
      this.dom.openPlanModal.style.display = "none";
    }
  }

  formatPlanDuration(seconds) {
    if (!seconds || isNaN(seconds)) return "0s";
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    if (m === 0) return `${s}s`;
    return `${m}m ${s.toString().padStart(2, "0")}s`;
  }

  formatPlanDate(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
    } catch (_) {
      return isoStr;
    }
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async fetchSavedPlans() {
    if (!this.dom.savedPlansList) return;
    this.dom.savedPlansList.innerHTML = `<div style="color: var(--text-dim); font-size: 12px; text-align: center; padding: 20px 0;">Loading plans...</div>`;

    try {
      const res = await fetch("/api/plans");
      let plans = [];
      if (res.ok) {
        plans = await res.json();
      }

      // Check local storage draft
      const localSaved = localStorage.getItem("pantiltlapse_saved_plan");
      let localPlan = null;
      if (localSaved) {
        try {
          localPlan = JSON.parse(localSaved);
        } catch (_) {}
      }

      if (plans.length === 0 && !localPlan) {
        this.dom.savedPlansList.innerHTML = `
          <div style="color: var(--text-dim); font-size: 12px; text-align: center; padding: 25px 10px; background: rgba(0,0,0,0.15); border-radius: 6px;">
            No saved plans found on rig.<br>Save your current plan first using 💾 Save.
          </div>
        `;
        return;
      }

      let html = "";

      // List server plans
      plans.forEach((p) => {
        const isCurrent = this.currentPlanId === p.id;
        const totalShots = p.total_shots || 240;
        const durationStr = this.formatPlanDuration(p.duration_s);
        const dateStr = this.formatPlanDate(p.updated_at || p.created_at);
        const safeName = this.escapeHtml(p.name || "Untitled Plan");

        html += `
          <div class="saved-plan-item" style="display: flex; justify-content: space-between; align-items: center; padding: 9px 12px; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: 6px;">
            <div style="overflow: hidden; padding-right: 8px;">
              <div style="font-weight: 600; font-size: 13px; color: var(--text-color); display: flex; align-items: center; gap: 6px;">
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${safeName}</span>
                ${isCurrent ? '<span style="font-size: 9px; padding: 1px 5px; border-radius: 3px; background: var(--primary-accent); color: #fff; font-weight: normal;">Active</span>' : ''}
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                ${totalShots} shots • ETA ${durationStr} • rev ${p.revision || 1} • ${dateStr}
              </div>
            </div>
            <div style="display: flex; gap: 6px; flex-shrink: 0;">
              <button class="btn btn-sm btn-primary" onclick="window.app.loadPlanFromServer('${p.id}')">Load</button>
              <button class="btn btn-sm btn-danger" style="padding: 4px 8px;" onclick="window.app.deletePlanFromServer('${p.id}', '${safeName}')" title="Delete Plan">✕</button>
            </div>
          </div>
        `;
      });

      // Add local browser draft option if present
      if (localPlan) {
        const localName = this.escapeHtml(localPlan.name || "Local Browser Session");
        html += `
          <div class="saved-plan-item" style="display: flex; justify-content: space-between; align-items: center; padding: 9px 12px; background: rgba(255,255,255,0.03); border: 1px dashed var(--border-color); border-radius: 6px; margin-top: 4px;">
            <div style="overflow: hidden; padding-right: 8px;">
              <div style="font-weight: 600; font-size: 13px; color: var(--text-color); display: flex; align-items: center; gap: 6px;">
                <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">📱 ${localName}</span>
                <span style="font-size: 9px; padding: 1px 5px; border-radius: 3px; background: rgba(255,255,255,0.1); color: var(--text-muted);">Browser Cache</span>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                ${localPlan.totalShots || 240} shots • ${localPlan.interval_s || 5}s interval
              </div>
            </div>
            <div style="display: flex; gap: 6px; flex-shrink: 0;">
              <button class="btn btn-sm btn-secondary" onclick="window.app.loadPlanFromLocalStorage()">Load Cache</button>
            </div>
          </div>
        `;
      }

      this.dom.savedPlansList.innerHTML = html;
    } catch (e) {
      this.dom.savedPlansList.innerHTML = `<div style="color: var(--status-error); font-size: 12px; padding: 12px; text-align: center;">Error loading plans: ${e}</div>`;
    }
  }

  async loadPlanFromServer(planId) {
    this.showToast("Loading plan from rig...", "info");
    try {
      const res = await fetch(`/api/plans/${planId}`);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        this.showToast(`Failed to load plan: ${err.detail?.message || res.statusText}`, "error");
        return;
      }
      const data = await res.json();
      this.applyLoadedPlan(data, true);
      this.closeOpenPlanModal();
    } catch (e) {
      this.showToast(`Load error: ${e}`, "error");
    }
  }

  loadPlanFromLocalStorage() {
    const saved = localStorage.getItem("pantiltlapse_saved_plan");
    if (!saved) {
      this.showToast("No cached plan in local storage", "warning");
      return;
    }
    try {
      const parsed = JSON.parse(saved);
      this.applyLoadedPlan(parsed, true);
      this.closeOpenPlanModal();
    } catch (e) {
      this.showToast(`Error loading cached plan: ${e}`, "error");
    }
  }

  async deletePlanFromServer(planId, name) {
    if (!confirm(`Delete saved plan "${name}"? This cannot be undone.`)) {
      return;
    }
    try {
      const res = await fetch(`/api/plans/${planId}`, { method: "DELETE" });
      if (res.ok) {
        if (this.currentPlanId === planId) {
          this.currentPlanId = null;
        }
        this.showToast(`Plan "${name}" deleted`, "info");
        await this.fetchSavedPlans();
      } else {
        const err = await res.json().catch(() => ({}));
        this.showToast(`Failed to delete plan: ${err.detail?.message || res.statusText}`, "error");
      }
    } catch (e) {
      this.showToast(`Delete error: ${e}`, "error");
    }
  }

  applyLoadedPlan(planData, showToastMessage = true) {
    if (!planData) return;

    // Check if rich studio plan is stored in acquisition.extra_settings.studio_plan
    const studioPlan = planData.acquisition?.extra_settings?.studio_plan;

    if (studioPlan) {
      this.plan.name = planData.name || studioPlan.name || "Timeline Sequence";
      this.plan.totalShots = studioPlan.totalShots || planData.schedule?.total_shots || 240;
      this.plan.interval_s = studioPlan.interval_s || planData.schedule?.interval_s || 5.0;
      this.plan.settle_time_s = studioPlan.settle_time_s !== undefined ? studioPlan.settle_time_s : (planData.schedule?.settle_time_s || 0.5);
      const isRaw = studioPlan.defaults?.raw !== undefined
        ? Boolean(studioPlan.defaults.raw)
        : (planData.acquisition?.camera_format ? planData.acquisition.camera_format.toUpperCase().includes("RAW") : false);
      this.plan.defaults = Object.assign({
        iso: "100", shutter_speed: "1/250", aperture: "4.0", white_balance: "Auto", raw: isRaw, image_format: isRaw ? "RAW + L" : "L"
      }, studioPlan.defaults || {
        iso: planData.acquisition?.iso,
        shutter_speed: planData.acquisition?.shutter_speed,
        aperture: planData.acquisition?.aperture,
        white_balance: planData.acquisition?.white_balance,
        raw: isRaw,
        image_format: isRaw ? "RAW + L" : "L"
      });
      this.plan.tracks = JSON.parse(JSON.stringify(studioPlan.tracks || {}));
    } else if (planData.tracks) {
      // LocalStorage format
      this.plan.name = planData.name || "Timeline Sequence";
      this.plan.totalShots = planData.totalShots || 240;
      this.plan.interval_s = planData.interval_s || 5.0;
      this.plan.settle_time_s = planData.settle_time_s !== undefined ? planData.settle_time_s : 0.5;
      const isRaw = planData.defaults?.raw !== undefined ? Boolean(planData.defaults.raw) : false;
      this.plan.defaults = Object.assign({
        iso: "100", shutter_speed: "1/250", aperture: "4.0", white_balance: "Auto", raw: isRaw, image_format: isRaw ? "RAW + L" : "L"
      }, planData.defaults || {});
      this.plan.tracks = JSON.parse(JSON.stringify(planData.tracks || {}));
    } else if (planData.trajectory) {
      // Canonical SequencePlan without studio_plan
      const total = Math.max(2, parseInt(planData.schedule?.total_shots) || 240);
      this.plan.name = planData.name || "Loaded Plan";
      this.plan.totalShots = total;
      this.plan.interval_s = Math.max(1.0, parseFloat(planData.schedule?.interval_s) || 5.0);
      this.plan.settle_time_s = Math.max(0.0, parseFloat(planData.schedule?.settle_time_s) || 0.5);
      const isRaw = planData.acquisition?.camera_format ? planData.acquisition.camera_format.toUpperCase().includes("RAW") : false;
      this.plan.defaults = {
        iso: planData.acquisition?.iso || "100",
        shutter_speed: planData.acquisition?.shutter_speed || "1/250",
        aperture: planData.acquisition?.aperture || "4.0",
        white_balance: planData.acquisition?.white_balance || "Auto",
        raw: isRaw,
        image_format: isRaw ? "RAW + L" : "L"
      };

      const convertKfs = (kfs, prefix) => {
        if (!kfs || kfs.length === 0) return [];
        return kfs.map((kf, i) => {
          let shotIndex = Math.round(kf.progress * (total - 1)) + 1;
          if (i === 0) shotIndex = 1;
          if (i === kfs.length - 1) shotIndex = total;
          return {
            id: kf.id || `${prefix}${i + 1}`,
            shotIndex,
            value: Number(kf.value) || 0.0,
            mode: kf.outgoing_mode || "auto",
            inTangent: [-15, 0],
            outTangent: [15, 0]
          };
        });
      };

      const panKfs = convertKfs(planData.trajectory?.pan_keyframes, "p");
      const tiltKfs = convertKfs(planData.trajectory?.tilt_keyframes, "t");

      this.plan.tracks = {
        pan: {
          id: "pan",
          label: "Pan Axis",
          color: "#06b6d4",
          unit: "deg",
          type: "continuous",
          keyframes: panKfs.length >= 2 ? panKfs : [
            { id: "p1", shotIndex: 1, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] },
            { id: "p2", shotIndex: total, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] }
          ]
        },
        tilt: {
          id: "tilt",
          label: "Tilt Axis",
          color: "#f97316",
          unit: "deg",
          type: "continuous",
          keyframes: tiltKfs.length >= 2 ? tiltKfs : [
            { id: "t1", shotIndex: 1, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] },
            { id: "t2", shotIndex: total, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] }
          ]
        }
      };
    }

    // Ensure minimum valid pan & tilt tracks exist
    if (!this.plan.tracks.pan || !this.plan.tracks.pan.keyframes || this.plan.tracks.pan.keyframes.length === 0) {
      this.plan.tracks.pan = {
        id: "pan",
        label: "Pan Axis",
        color: "#06b6d4",
        unit: "deg",
        type: "continuous",
        keyframes: [
          { id: "p1", shotIndex: 1, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] },
          { id: "p2", shotIndex: this.plan.totalShots, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] }
        ]
      };
    }
    if (!this.plan.tracks.tilt || !this.plan.tracks.tilt.keyframes || this.plan.tracks.tilt.keyframes.length === 0) {
      this.plan.tracks.tilt = {
        id: "tilt",
        label: "Tilt Axis",
        color: "#f97316",
        unit: "deg",
        type: "continuous",
        keyframes: [
          { id: "t1", shotIndex: 1, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] },
          { id: "t2", shotIndex: this.plan.totalShots, value: 0.0, mode: "auto", inTangent: [-15, 0], outTangent: [15, 0] }
        ]
      };
    }

    // Update DOM inputs
    if (this.dom.planNameInput) this.dom.planNameInput.value = this.plan.name;
    if (this.dom.totalShotsInput) this.dom.totalShotsInput.value = this.plan.totalShots;
    if (this.dom.totalShotsLabel) this.dom.totalShotsLabel.textContent = this.plan.totalShots;
    if (this.dom.playheadInput) this.dom.playheadInput.max = this.plan.totalShots;
    if (this.dom.intervalInput) this.dom.intervalInput.value = this.plan.interval_s;
    if (this.dom.settleInput) this.dom.settleInput.value = this.plan.settle_time_s;

    if (this.dom.defaultIsoSelect && this.plan.defaults.iso) {
      this.dom.defaultIsoSelect.value = this.plan.defaults.iso;
    }
    if (this.dom.defaultShutterSelect && this.plan.defaults.shutter_speed) {
      this.dom.defaultShutterSelect.value = this.plan.defaults.shutter_speed;
    }
    if (this.dom.defaultApertureSelect && this.plan.defaults.aperture) {
      this.dom.defaultApertureSelect.value = this.plan.defaults.aperture;
    }
    if (this.dom.defaultWbSelect && this.plan.defaults.white_balance) {
      this.dom.defaultWbSelect.value = this.plan.defaults.white_balance;
    }
    this.updateRawUI();

    this.currentPlanId = planData.id || null;
    this.currentPlanRevision = planData.revision || 1;

    // Reset playback & track views
    this.setPlayhead(1);
    this.updateScheduleCalculations();
    this.checkShutterIntervalSafety();
    this.renderTrackHeaders();

    this.activeTrackId = "pan";
    this.selectedKeyId = this.plan.tracks.pan.keyframes[0]?.id || null;
    this.updateInspectorUI();
    this.renderTimeline();
    this.updateOverlays();

    // Persist in localStorage
    localStorage.setItem("pantiltlapse_saved_plan", JSON.stringify(this.plan));

    // Update backend active plan if applicable
    if (this.currentPlanId) {
      fetch("/api/app/state", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_plan_id: this.currentPlanId })
      }).catch(() => {});
    }

    if (showToastMessage) {
      this.showToast(`Plan "${this.plan.name}" loaded successfully`, "success");
    }
  }

  async loadInitialPlan() {
    // 1. Immediately check local storage cache to restore instantly without UI flickers
    const localSaved = localStorage.getItem("pantiltlapse_saved_plan");
    if (localSaved) {
      try {
        const parsed = JSON.parse(localSaved);
        if (parsed && (parsed.tracks || parsed.trajectory)) {
          this.applyLoadedPlan(parsed, false);
        }
      } catch (e) {
        console.warn("Failed to parse cached local plan:", e);
      }
    }

    // 2. Query rig backend active plan from /api/app/state
    try {
      const stateRes = await fetch("/api/app/state");
      if (stateRes.ok) {
        const stateData = await stateRes.json();
        if (stateData.active_plan_id && stateData.active_plan_id !== this.currentPlanId) {
          const planRes = await fetch(`/api/plans/${stateData.active_plan_id}`);
          if (planRes.ok) {
            const planData = await planRes.json();
            this.applyLoadedPlan(planData, false);
          }
        }
      }
    } catch (_) {}
  }

  showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.style.cursor = "pointer";
    toast.title = "Click to dismiss";
    toast.innerHTML = `<span>${message}</span><span style="margin-left: 10px; opacity: 0.6; font-size: 10px;">✕</span>`;
    toast.onclick = () => toast.remove();
    this.dom.toastContainer.appendChild(toast);
    setTimeout(() => {
      if (toast.parentNode) toast.remove();
    }, 2800);
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
  const banner = document.getElementById("execZeroWarningBanner");
  if (banner) banner.style.display = "none";
  try {
    const res = await fetch("/api/rig/confirm-zero", { method: "POST" });
    const data = await res.json();
    if (data.status === "OK") {
      if (banner) banner.style.display = "none";
      if (window.app) {
        window.app.showToast("Zero reference confirmed (0.00°, 0.00°)", "success");
        const ref = data.reference || { confirmed: true, reference_confirmed: true };
        window.app.handleLiveEvent({ reference: ref, motors: data.motors });
      }
    } else {
      if (banner) banner.style.display = "flex";
      if (window.app) window.app.showToast(`Zero confirmation failed: ${data.message || "Unknown error"}`, "error");
    }
  } catch (e) {
    if (banner) banner.style.display = "flex";
    if (window.app) window.app.showToast(`Zero error: ${e}`, "error");
  }
};

window.closeOffsetChoiceModal = function() {
  const m = document.getElementById("offsetChoiceModal");
  if (m) m.style.display = "none";
};

window.closeOpenPlanModal = function() {
  if (window.app) {
    window.app.closeOpenPlanModal();
  } else {
    const m = document.getElementById("openPlanModal");
    if (m) m.style.display = "none";
  }
};
