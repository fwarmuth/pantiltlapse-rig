import asyncio
import logging
import os
import subprocess
import time
from typing import Any

try:
    import gphoto2 as gp

    HAS_GPHOTO2 = True
except ImportError:
    HAS_GPHOTO2 = False

logger = logging.getLogger("CameraCommander.Camera")


def get_noncolliding_stem(dest_dir: str, base_stem: str, extensions: list[str]) -> str:
    """Find a stem such that dest_dir / f'{candidate_stem}{ext}' does not exist for any extension in extensions."""
    candidate_stem = base_stem
    counter = 1
    while any(os.path.exists(os.path.join(dest_dir, f"{candidate_stem}{ext}")) for ext in extensions):
        candidate_stem = f"{base_stem}_{counter:02d}"
        counter += 1
    return candidate_stem


class CameraManager:
    """
    Manages Canon DSLR camera control via native python-gphoto2 C-bindings.
    Maintains a persistent camera session for fast, zero-latency shutter releases.
    Does NOT include silent fake fallback. If gphoto2 fails, connection fails explicitly.
    """

    def __init__(self, capture_dir: str = "output/captures"):
        self.capture_dir = os.path.abspath(capture_dir)
        os.makedirs(self.capture_dir, exist_ok=True)

        self.model = "Unknown"
        self.is_connected = False
        self.exposure_mode = "Unknown"
        self.iso = "400"
        self.shutter_speed = "1/125"
        self.aperture = "5.6"
        self.white_balance = "Auto"
        self.image_format = os.getenv("IMAGE_FORMAT", "RAW + L" if os.getenv("CAPTURE_RAW", "").lower() in ("true", "1", "yes") else "L")
        self.focus_mode = "Unknown"
        self._pending_focus_actions: list[str] = []
        self.latest_photo_path: str | None = None
        self.last_capture_time: float = 0.0

        self._camera: Any = None
        self._lock = asyncio.Lock()
        self._is_restarting = False

    @property
    def is_manual_mode(self) -> bool:
        """Return True if camera physical dial is in Manual mode ('Manual' or 'M')."""
        return self.exposure_mode.strip().lower() in ("manual", "m")

    def _rehydrate_latest_photo(self):
        """Find most recent photo file in capture directory if latest_photo_path is empty."""
        if not self.latest_photo_path and os.path.exists(self.capture_dir):
            try:
                candidate_files = []
                for root, _, files in os.walk(self.capture_dir):
                    if os.path.basename(root).startswith("."):
                        continue
                    for f in files:
                        if f.lower().endswith((".jpg", ".jpeg", ".cr2", ".cr3")):
                            full_path = os.path.join(root, f)
                            candidate_files.append((os.path.getmtime(full_path), full_path))
                if candidate_files:
                    candidate_files.sort(key=lambda x: x[0], reverse=True)
                    self.latest_photo_path = candidate_files[0][1]
                    self.last_capture_time = candidate_files[0][0]
                    logger.info(f"Rehydrated latest photo path on startup: '{self.latest_photo_path}'")
            except Exception as e:
                logger.debug(f"Could not rehydrate latest photo path: {e}")

    async def initialize(self) -> bool:
        self._rehydrate_latest_photo()
        if not HAS_GPHOTO2:
            logger.error("python-gphoto2 package is not installed. CameraManager unavailable.")
            self.is_connected = False
            return False

        return await self.connect_camera()

    async def connect_camera(self) -> bool:
        """Initialize persistent gphoto2 camera session asynchronously off main event loop."""
        async with self._lock:
            if not HAS_GPHOTO2:
                self.is_connected = False
                return False

            def _init_gphoto():
                cam = None
                try:
                    logger.info("Initializing persistent python-gphoto2 session...")
                    cam = gp.Camera()
                    cam.init()
                    model_name = "Canon EOS DSLR"
                    summary = cam.get_summary()
                    summary_str = str(summary)
                    for line in summary_str.splitlines():
                        if "Manufacturer:" in line or "Model:" in line:
                            model_name = line.strip()
                            break
                    return cam, model_name
                except Exception as e:
                    logger.error(f"Failed to open native gphoto2 camera session: {e}")
                    if cam is not None:
                        try:
                            cam.exit()
                        except Exception:
                            pass
                        del cam
                    import gc
                    gc.collect()
                    return None, "Disconnected"

            cam, model_name = await asyncio.to_thread(_init_gphoto)
            if not cam:
                self.is_connected = False
                self.model = "Disconnected"
                self._camera = None
                return False

            self._camera = cam
            self.is_connected = True
            self.model = model_name
            logger.info(f"Connected to persistent camera session: '{self.model}'")

            def _init_clean_state():
                try:
                    if hasattr(cam, "get_single_config") and hasattr(cam, "set_single_config"):
                        try:
                            eos = cam.get_single_config("eosremoterelease")
                            eos.set_value("Release")
                            cam.set_single_config("eosremoterelease", eos)
                        except Exception:
                            pass
                    else:
                        cfg = cam.get_config()
                        eos = self._find_widget_recursive(cfg, "eosremoterelease")
                        if eos:
                            eos.set_value("Release")
                            cam.set_config(cfg)
                except Exception:
                    pass
            await asyncio.to_thread(_init_clean_state)

            await asyncio.to_thread(self._read_configs_nolock)
            return True

    def _read_configs_nolock(self):
        """Read ISO, shutter speed, aperture, and exposure mode directly from native C config tree."""
        if not self._camera:
            return
        try:
            config = self._camera.get_config()
            try:
                self.iso = str(config.get_child_by_name("iso").get_value())
            except Exception:
                pass
            try:
                self.shutter_speed = str(config.get_child_by_name("shutterspeed").get_value())
            except Exception:
                pass
            try:
                self.aperture = str(config.get_child_by_name("aperture").get_value())
            except Exception:
                pass
            try:
                w_wb = self._find_widget_recursive(config, "whitebalance")
                if w_wb is not None:
                    self.white_balance = str(w_wb.get_value())
            except Exception:
                pass
            try:
                w_mode = self._find_widget_recursive(config, "autoexposuremode")
                if w_mode is None:
                    w_mode = self._find_widget_recursive(config, "expprogram")
                if w_mode is not None:
                    self.exposure_mode = str(w_mode.get_value())
                    if not self.is_manual_mode:
                        logger.warning(
                            f"Camera dial is in '{self.exposure_mode}' mode. Exposure controls (ISO/shutter/aperture) "
                            f"will be restricted by camera firmware. Turn dial to 'M' (Manual) for full control."
                        )
            except Exception:
                pass
            try:
                w_fm = self._find_widget_recursive(config, "focusmode")
                if w_fm is not None:
                    self.focus_mode = str(w_fm.get_value())
                    if self.focus_mode.lower() in ("manual", "mf"):
                        logger.warning(
                            "Camera reports lens focusmode='Manual'. Note: The physical switch on the lens barrel "
                            "must be set to 'AF' for software electronic manual focus steps to drive the lens motor."
                        )
            except Exception:
                pass
            try:
                w_if = self._find_widget_recursive(config, "imageformat") or self._find_widget_recursive(config, "imageformatsd")
                if w_if is not None:
                    self.image_format = str(w_if.get_value())
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error reading camera configs: {e}")

    async def refresh_config(self) -> dict[str, Any]:
        """Refresh exposure settings from active camera session."""
        if not self.is_connected or not self._camera:
            return {
                "iso": self.iso,
                "shutter_speed": self.shutter_speed,
                "aperture": self.aperture,
                "white_balance": self.white_balance,
                "exposure_mode": self.exposure_mode,
                "image_format": self.image_format,
                "raw_enabled": "RAW" in (self.image_format or "").upper(),
            }

        async with self._lock:
            self._read_configs_nolock()

        return {
            "iso": self.iso,
            "shutter_speed": self.shutter_speed,
            "aperture": self.aperture,
            "white_balance": self.white_balance,
            "exposure_mode": self.exposure_mode,
            "image_format": self.image_format,
            "raw_enabled": "RAW" in (self.image_format or "").upper(),
        }

    async def apply_startup_defaults(self):
        """Set startup camera acquisition defaults (Auto ISO, auto/sensible shutter, and aperture ~4.5)."""
        if not self.is_connected or not self._camera:
            return

        try:
            choices = await self.get_config_choices()

            # 1. ISO: Prefer 'Auto' if supported
            iso_choices = choices.get("iso", [])
            for candidate in ["Auto", "auto", "AUTO"]:
                if candidate in iso_choices:
                    await self.set_config("iso", candidate)
                    break

            # 2. Aperture: Set ~4.5 (or closest available aperture)
            ap_choices = choices.get("aperture", [])
            for candidate in ["4.5", "4.0", "5.0", "5.6", "4", "5", "f/4.5", "f/4.0", "f/5.6"]:
                clean = candidate.replace("f/", "").replace("F/", "")
                if clean in ap_choices or candidate in ap_choices:
                    await self.set_config("aperture", clean)
                    break

            # 3. Shutter speed: Prefer 'Auto' if supported
            shutter_choices = choices.get("shutter_speed", [])
            for candidate in ["Auto", "auto", "AUTO"]:
                if candidate in shutter_choices:
                    await self.set_config("shutter_speed", candidate)
                    break

            # 4. Image format / RAW: Apply CAPTURE_RAW or IMAGE_FORMAT if configured
            target_fmt = os.getenv("IMAGE_FORMAT")
            if not target_fmt:
                capture_raw_env = os.getenv("CAPTURE_RAW")
                if capture_raw_env is not None:
                    target_fmt = "RAW + L" if capture_raw_env.lower() in ("true", "1", "yes") else "L"
            if target_fmt:
                await self.set_config("image_format", target_fmt)

            await self.refresh_config()
            logger.info(
                f"Startup camera defaults applied: ISO={self.iso}, Shutter={self.shutter_speed}, "
                f"Aperture={self.aperture}, Format={self.image_format}"
            )
        except Exception as e:
            logger.warning(f"Could not apply all startup camera defaults: {e}")

    async def get_config_choices(self) -> dict[str, list[str]]:
        """
        Query native gPhoto2 camera widget choices for iso, shutterspeed, and aperture.
        If camera is disconnected, raises Exception (explicit failure, no silent fallbacks).
        """
        if not self.is_connected or not self._camera:
            raise Exception("Camera is disconnected. Connect real camera or enable FAKE_CAMERA=true in .env")

        async with self._lock:
            try:
                config = self._camera.get_config()
                key_map = {
                    "iso": "iso",
                    "shutter_speed": "shutterspeed",
                    "aperture": "aperture",
                    "white_balance": "whitebalance",
                    "image_format": "imageformat",
                }
                choices: dict[str, list[str]] = {}
                for param, child_name in key_map.items():
                    try:
                        child = self._find_widget_recursive(config, child_name)
                        if child is None and child_name == "imageformat":
                            child = self._find_widget_recursive(config, "imageformatsd")
                        if child is not None:
                            count = child.count_choices()
                            param_choices = [str(child.get_choice(i)) for i in range(count)]
                            choices[param] = param_choices
                        else:
                            choices[param] = []
                    except Exception as e:
                        logger.warning(f"Could not read choices for widget '{child_name}': {e}")
                        choices[param] = []

                return choices
            except Exception as e:
                logger.error(f"Error reading camera config choices: {e}")
                raise Exception(f"Failed to query camera config choices: {e}") from e

    async def set_config(self, param: str, value: str) -> dict[str, Any]:
        """Set ISO, shutter speed, aperture, white balance, or image format (RAW/JPEG)."""
        if param == "raw":
            param = "image_format"
            val_bool = str(value).lower() in ("true", "1", "yes", "on")
            value = "RAW + L" if val_bool else "L"

        key_map = {
            "iso": "iso",
            "shutter_speed": "shutterspeed",
            "aperture": "aperture",
            "white_balance": "whitebalance",
            "image_format": "imageformat",
        }
        if param not in key_map:
            return {"status": "ERROR", "message": f"Unsupported parameter '{param}'"}

        child_name = key_map[param]
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        val_str = str(value)
        if param == "aperture":
            val_str = val_str.replace("f/", "").replace("F/", "").strip()

        # If parameter is already at target value, skip USB overhead
        if getattr(self, param, None) == val_str:
            return {"status": "OK", "param": param, "value": val_str, "unchanged": True}

        async with self._lock:
            try:
                def _apply_config():
                    if hasattr(self._camera, "get_single_config") and hasattr(self._camera, "set_single_config"):
                        child = self._camera.get_single_config(child_name)
                        child.set_value(val_str)
                        self._camera.set_single_config(child_name, child)
                    else:
                        config = self._camera.get_config()
                        child = self._find_widget_recursive(config, child_name)
                        if child is None:
                            raise Exception(f"Widget '{child_name}' not found on camera")
                        child.set_value(val_str)
                        self._camera.set_config(config)

                await asyncio.to_thread(_apply_config)
                setattr(self, param, val_str)
                logger.info(f"Updated camera config '{param}' -> '{val_str}'")
                return {"status": "OK", "param": param, "value": val_str}
            except Exception as e:
                logger.error(f"Failed to set camera config '{param}' to '{val_str}': {e}")
                return {"status": "ERROR", "message": str(e)}

    def _find_widget_recursive(self, root: Any, target_name: str) -> Any | None:
        """Find a widget by name anywhere in the hierarchical gphoto2 configuration tree."""
        if root is None:
            return None
        try:
            if root.get_name() == target_name:
                return root
        except Exception:
            pass
        try:
            count = root.count_children()
        except Exception:
            return None
        for i in range(count):
            try:
                child = root.get_child(i)
                found = self._find_widget_recursive(child, target_name)
                if found is not None:
                    return found
            except Exception:
                pass
        return None

    def _find_focus_widget(self, root: Any) -> tuple[Any | None, str | None]:
        """Search for focus drive widgets by standard names or substring match."""
        candidates = ["manualfocusdrive", "focusdrive", "autofocusdrive", "d034", "eoszoom", "focus"]
        for cand in candidates:
            w = self._find_widget_recursive(root, cand)
            if w is not None:
                return w, cand

        # Fallback: traverse all widgets for partial name match
        all_widgets = []
        self._extract_widgets_recursive(root, all_widgets)
        for item in all_widgets:
            n = item.get("name", "").lower()
            if "focus" in n and ("drive" in n or "step" in n or "manual" in n):
                w = self._find_widget_recursive(root, item["name"])
                if w is not None:
                    return w, item["name"]

        return None, None

    async def step_focus(self, direction: str, step_size: int = 1) -> dict[str, Any]:
        """
        Drive camera manual focus in discrete steps ('near' or 'far', step_size 1..3).
        Searches entire hierarchical config tree recursively for focus drive widget.
        """
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        direction = direction.lower()
        if direction not in ("near", "far"):
            return {"status": "ERROR", "message": "Direction must be 'near' or 'far'"}
        step_size = max(1, min(3, int(step_size)))
        drive_str = f"{direction.capitalize()} {step_size}"

        if self.focus_mode.lower() in ("manual", "mf"):
            logger.warning(
                "Camera reports lens focusmode='Manual'. Note: The physical switch on the lens barrel "
                "must be set to 'AF' for software electronic manual focus steps to drive the lens motor."
            )

        async with self._lock:
            def _drive_focus():
                try:
                    widget = None
                    widget_name = None
                    choices = []

                    # 1. Prefer get_single_config for manualfocusdrive
                    if hasattr(self._camera, "get_single_config") and hasattr(self._camera, "set_single_config"):
                        for cand in ["manualfocusdrive", "focusdrive"]:
                            try:
                                w = self._camera.get_single_config(cand)
                                if w is not None:
                                    widget = w
                                    widget_name = cand
                                    break
                            except Exception:
                                pass

                    # 2. Fallback to searching full tree if single config didn't find it
                    full_cfg = None
                    if widget is None:
                        full_cfg = self._camera.get_config()
                        widget, widget_name = self._find_focus_widget(full_cfg)

                    if widget is None or widget_name is None:
                        return {
                            "status": "ERROR",
                            "message": "Camera does not expose a focus drive widget.",
                            "hint": "Check /debug/camera widget tree to view available controls.",
                        }

                    try:
                        count = widget.count_choices()
                        for i in range(count):
                            choices.append(str(widget.get_choice(i)))
                    except Exception:
                        pass

                    target_val = drive_str
                    if choices:
                        matched = False
                        # Exact / case-insensitive match
                        for c in choices:
                            if c.lower() == drive_str.lower():
                                target_val = c
                                matched = True
                                break
                        # Direction & step_size substring match
                        if not matched:
                            for c in choices:
                                if direction in c.lower() and str(step_size) in c:
                                    target_val = c
                                    matched = True
                                    break
                        # Signed integer match (-3..+3)
                        if not matched:
                            signed_str = f"-{step_size}" if direction == "far" else str(step_size)
                            for c in choices:
                                if c == signed_str or c == f"+{step_size}":
                                    target_val = c
                                    matched = True
                                    break

                    # Check / ensure viewfinder (Live View) on Canon EOS cameras.
                    # Canon PTP firmware ignores manualfocusdrive if the reflex mirror is down.
                    vf_widget = None
                    vf_needed_restore = False
                    if hasattr(self._camera, "get_single_config") and hasattr(self._camera, "set_single_config"):
                        try:
                            vf = self._camera.get_single_config("viewfinder")
                            if vf is not None:
                                curr_vf = vf.get_value()
                                if curr_vf == 0 or str(curr_vf) == "0":
                                    logger.info("Enabling Canon viewfinder (Live View) for manual focus drive...")
                                    vf.set_value(1)
                                    self._camera.set_single_config("viewfinder", vf)
                                    vf_widget = vf
                                    vf_needed_restore = True
                                    time.sleep(0.2)  # Allow reflex mirror to lift and AF motor circuit to activate
                        except Exception as e:
                            logger.info(f"Viewfinder pre-step handling exception: {e}")

                    try:
                        widget.set_value(target_val)
                    except Exception:
                        val_num = step_size if direction == "near" else -step_size
                        widget.set_value(val_num)

                    # Apply via single config if available to avoid sending full tree
                    if hasattr(self._camera, "set_single_config") and widget_name:
                        self._camera.set_single_config(widget_name, widget)
                    elif full_cfg is not None:
                        self._camera.set_config(full_cfg)
                    else:
                        cfg = self._camera.get_config()
                        w = self._find_widget_recursive(cfg, widget_name)
                        if w:
                            w.set_value(target_val)
                            self._camera.set_config(cfg)

                    # Allow mechanical lens DC motor travel to settle before returning
                    settle_sec = 0.25 if step_size == 1 else (0.35 if step_size == 2 else 0.5)
                    try:
                        context = gp.Context()
                        t_end = time.time() + settle_sec
                        while time.time() < t_end:
                            evt_type, _ = self._camera.wait_for_event(50, context)
                            if evt_type == gp.GP_EVENT_TIMEOUT:
                                pass
                    except Exception:
                        time.sleep(settle_sec)

                    # Restore viewfinder to standby if we temporarily lifted the mirror
                    if vf_needed_restore and vf_widget is not None:
                        try:
                            vf_widget.set_value(0)
                            self._camera.set_single_config("viewfinder", vf_widget)
                            logger.info("Restored Canon viewfinder to standby (0)")
                        except Exception as e:
                            logger.info(f"Viewfinder post-step restore handling exception: {e}")

                    # Note: Do NOT set manualfocusdrive="None".
                    # In Canon PTP, manualfocusdrive is an action trigger that automatically resets.
                    self._pending_focus_actions.append(f"{direction.capitalize()} {step_size}")

                    logger.info(f"Manual focus step applied: widget={widget_name}, value={target_val}")
                    return {
                        "status": "OK",
                        "widget": widget_name,
                        "direction": direction,
                        "step_size": step_size,
                        "applied_value": str(target_val),
                        "available_choices": choices,
                    }
                except Exception as e:
                    logger.error(f"Manual focus step failed: {e}")
                    return {"status": "ERROR", "message": str(e), "attempted_value": drive_str}

            return await asyncio.to_thread(_drive_focus)

    async def trigger_autofocus(self) -> dict[str, Any]:
        """Trigger camera autofocus lock."""
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        async with self._lock:
            def _do_autofocus():
                try:
                    config = self._camera.get_config()
                    widget = self._find_widget_recursive(
                        config, "autofocusdrive"
                    ) or self._find_widget_recursive(config, "autofocus")

                    if widget:
                        try:
                            widget.set_value(1)
                        except Exception:
                            widget.set_value("1")
                        self._camera.set_config(config)
                        return {"status": "OK", "message": "Autofocus triggered"}
                    else:
                        return {"status": "ERROR", "message": "Camera does not support autofocus drive widget"}
                except Exception as e:
                    return {"status": "ERROR", "message": str(e)}

            return await asyncio.to_thread(_do_autofocus)

    async def get_all_widgets(self) -> list[dict[str, Any]]:
        """Extract flat list of all configuration widgets from connected camera."""
        if not self.is_connected or not self._camera:
            return []

        async with self._lock:
            def _scan():
                result = []
                try:
                    config = self._camera.get_config()
                    self._extract_widgets_recursive(config, result)
                except Exception as e:
                    logger.error(f"Error reading camera widget tree: {e}")
                return result

            return await asyncio.to_thread(_scan)

    def _extract_widgets_recursive(self, widget: Any, out_list: list[dict[str, Any]]):
        if widget is None:
            return
        try:
            name = widget.get_name()
            label = widget.get_label()
            w_type = str(widget.get_type())
            readonly = widget.get_readonly() == 1

            val = None
            try:
                val = str(widget.get_value())
            except Exception:
                pass

            choices = []
            try:
                count = widget.count_choices()
                for i in range(count):
                    choices.append(str(widget.get_choice(i)))
            except Exception:
                pass

            out_list.append({
                "name": name,
                "label": label,
                "type": w_type,
                "value": val,
                "readonly": readonly,
                "choices": choices,
            })
        except Exception:
            pass

        try:
            for i in range(widget.count_children()):
                self._extract_widgets_recursive(widget.get_child(i), out_list)
        except Exception:
            pass

    async def set_raw_widget(self, name: str, value: Any) -> dict[str, Any]:
        """Set any camera widget directly by name anywhere in tree for debugging."""
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        async with self._lock:
            def _set():
                try:
                    if hasattr(self._camera, "get_single_config") and hasattr(self._camera, "set_single_config"):
                        try:
                            widget = self._camera.get_single_config(name)
                            if widget is not None:
                                try:
                                    widget.set_value(value)
                                except Exception:
                                    try:
                                        widget.set_value(int(value))
                                    except Exception:
                                        widget.set_value(str(value))
                                self._camera.set_single_config(name, widget)
                                logger.info(f"Debug raw widget set via single_config: '{name}' = {value}")
                                return {"status": "OK", "widget": name, "value": value}
                        except Exception:
                            pass

                    config = self._camera.get_config()
                    widget = self._find_widget_recursive(config, name)
                    if not widget:
                        return {"status": "ERROR", "message": f"Widget '{name}' not found on camera"}

                    try:
                        widget.set_value(value)
                    except Exception:
                        try:
                            widget.set_value(str(value))
                        except Exception:
                            widget.set_value(int(value))

                    self._camera.set_config(config)
                    logger.info(f"Debug raw widget set: '{name}' = {value}")
                    return {"status": "OK", "widget": name, "value": value}
                except Exception as e:
                    logger.error(f"Failed to set raw widget '{name}' to {value}: {e}")
                    return {"status": "ERROR", "message": str(e)}

            return await asyncio.to_thread(_set)

    @staticmethod
    def _estimate_exposure_seconds(shutter_speed_str: str) -> float:
        try:
            s = str(shutter_speed_str).strip().lower()
            if "/" in s:
                parts = s.split("/", 1)
                return float(parts[0]) / float(parts[1])
            return float(s)
        except Exception:
            return 0.5

    async def trigger_capture(self, filename: str | None = None, target_dir: str | None = None) -> dict[str, Any]:
        """Trigger shutter release and save photo preserving real camera extension."""
        if not self.is_connected or not self._camera:
            return {"status": "ERROR", "message": "Camera is disconnected"}

        dest_dir = os.path.abspath(target_dir) if target_dir else self.capture_dir
        os.makedirs(dest_dir, exist_ok=True)

        async with self._lock:
            try:
                logger.info("Triggering native gphoto2 shutter release...")

                def _do_gphoto_capture():
                    file_path = None
                    used_eos_mf = False

                    # 1. On Canon EOS cameras, use 'Press Full MF' to release shutter without triggering AF
                    try:
                        eos_release = None
                        choices = []

                        if hasattr(self._camera, "get_single_config") and hasattr(self._camera, "set_single_config"):
                            try:
                                eos_release = self._camera.get_single_config("eosremoterelease")
                            except Exception:
                                eos_release = None

                        full_cfg = None
                        if eos_release is None:
                            full_cfg = self._camera.get_config()
                            eos_release = self._find_widget_recursive(full_cfg, "eosremoterelease")

                        if eos_release is not None:
                            try:
                                for i in range(eos_release.count_choices()):
                                    choices.append(str(eos_release.get_choice(i)))
                            except Exception:
                                pass

                            if "Press Full MF" in choices:
                                used_eos_mf = True
                                logger.info("Triggering shutter via Canon EOS remoterelease 'Press Full MF' (pure manual focus release)...")
                                try:
                                    pre_ctx = gp.Context()
                                    t_pre = time.time() + 0.1
                                    while time.time() < t_pre:
                                        evt, _ = self._camera.wait_for_event(20, pre_ctx)
                                        if evt == gp.GP_EVENT_TIMEOUT:
                                            break
                                except Exception:
                                    pass

                                eos_release.set_value("Press Full MF")
                                if hasattr(self._camera, "set_single_config"):
                                    self._camera.set_single_config("eosremoterelease", eos_release)
                                elif full_cfg is not None:
                                    self._camera.set_config(full_cfg)
                                else:
                                    cfg = self._camera.get_config()
                                    w = self._find_widget_recursive(cfg, "eosremoterelease")
                                    if w:
                                        w.set_value("Press Full MF")
                                        self._camera.set_config(cfg)

                                # Wait for GP_EVENT_FILE_ADDED event(s)
                                # Dynamically scale timeout based on exposure time
                                exp_sec = self._estimate_exposure_seconds(self.shutter_speed)
                                max_wait = max(15.0, exp_sec * 2.5 + 8.0)
                                context = gp.Context()
                                start_wait = time.time()
                                captured_events = []
                                try:
                                    while time.time() - start_wait < max_wait:
                                        evt_type, evt_data = self._camera.wait_for_event(100, context)
                                        if evt_type == gp.GP_EVENT_FILE_ADDED:
                                            captured_events.append(evt_data)
                                            # In dual RAW+JPEG mode, camera emits 2 file added events; wait up to 2.5s for companion
                                            if "RAW" in (self.image_format or "").upper():
                                                dual_deadline = time.time() + 2.5
                                                while time.time() < dual_deadline:
                                                    sub_type, sub_data = self._camera.wait_for_event(100, context)
                                                    if sub_type == gp.GP_EVENT_FILE_ADDED:
                                                        captured_events.append(sub_data)
                                                        break
                                            break
                                finally:
                                    # ALWAYS release the shutter button completely using 'Release'
                                    try:
                                        rel_val = "Release" if "Release" in choices else "Release Full"
                                        if hasattr(self._camera, "get_single_config") and hasattr(self._camera, "set_single_config"):
                                            rel_w = self._camera.get_single_config("eosremoterelease")
                                            rel_w.set_value(rel_val)
                                            self._camera.set_single_config("eosremoterelease", rel_w)
                                        else:
                                            cfg = self._camera.get_config()
                                            rel_w = self._find_widget_recursive(cfg, "eosremoterelease")
                                            if rel_w:
                                                rel_w.set_value(rel_val)
                                                self._camera.set_config(cfg)
                                    except Exception as e:
                                        logger.warning(f"Could not reset eosremoterelease: {e}")

                                    # Drain post-capture property events so camera state is clean
                                    drain_start = time.time()
                                    while time.time() - drain_start < 2.0:
                                        evt_type, _ = self._camera.wait_for_event(50, context)
                                        if evt_type == gp.GP_EVENT_TIMEOUT:
                                            break
                    except Exception as e:
                        logger.warning(f"Canon EOS Press Full MF capture failed: {e}")

                    # 2. Fallback: NEVER fallback to camera.capture if Press Full MF was attempted
                    if not captured_events:
                        if used_eos_mf:
                            raise Exception(f"Canon EOS capture timed out waiting for image event (exposure: {self.shutter_speed}s)")
                        single_path = self._camera.capture(gp.GP_CAPTURE_IMAGE)
                        captured_events.append(single_path)

                    if filename:
                        base_stem = os.path.splitext(filename)[0]
                    else:
                        timestamp = time.strftime("%Y%m%d_%H%M%S")
                        base_stem = f"capture_{timestamp}"

                    event_exts = [os.path.splitext(fp.name)[1].lower() or ".jpg" for fp in captured_events] or [".jpg"]
                    stem = get_noncolliding_stem(dest_dir, base_stem, event_exts)

                    saved_files = []
                    raw_exts = (".cr2", ".cr3", ".nef", ".arw", ".dng")

                    for fp in captured_events:
                        cam_ext = os.path.splitext(fp.name)[1].lower() or ".jpg"
                        save_name = f"{stem}{cam_ext}"
                        target_file = os.path.join(dest_dir, save_name)
                        camera_file = self._camera.file_get(fp.folder, fp.name, gp.GP_FILE_TYPE_NORMAL)
                        camera_file.save(target_file)
                        try:
                            self._camera.file_delete(fp.folder, fp.name)
                        except Exception:
                            pass
                        is_raw = cam_ext in raw_exts
                        saved_files.append((save_name, target_file, cam_ext, is_raw))

                    # Choose primary displayable image (prefer JPEG for viewport/previews)
                    jpg_candidates = [f for f in saved_files if not f[3]]
                    raw_candidates = [f for f in saved_files if f[3]]

                    primary_file = jpg_candidates[0] if jpg_candidates else saved_files[0]
                    raw_file = raw_candidates[0] if raw_candidates else None

                    primary_save_name, primary_target_file, primary_cam_ext, _ = primary_file
                    raw_save_name, raw_target_file, _, _ = raw_file if raw_file else (None, None, None, None)

                    return (
                        primary_save_name,
                        primary_target_file,
                        primary_cam_ext,
                        raw_save_name,
                        raw_target_file,
                        [s[0] for s in saved_files],
                    )

                (
                    save_name,
                    target_file,
                    cam_ext,
                    raw_save_name,
                    raw_target_file,
                    all_file_names,
                ) = await asyncio.to_thread(_do_gphoto_capture)

                self.latest_photo_path = target_file
                self.last_capture_time = time.time()
                logger.info(f"Photo captured: primary='{target_file}', raw='{raw_target_file}'")

                mime_map = {
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".cr2": "image/x-canon-cr2",
                    ".cr3": "image/x-canon-cr3",
                    ".nef": "image/x-nikon-nef",
                    ".arw": "image/x-sony-arw",
                }
                mime_type = mime_map.get(cam_ext, "application/octet-stream")

                result = {
                    "camera_filename": save_name,
                    "saved_original_path": target_file,
                    "extension": cam_ext,
                    "mime_type": mime_type,
                    "capture_timestamp": self.last_capture_time,
                    "camera_preview_path": None,
                    "has_raw": bool(raw_target_file),
                    "raw_filename": raw_save_name,
                    "raw_path": raw_target_file,
                    "all_files": all_file_names,
                }

                return {
                    "status": "OK",
                    "filename": save_name,
                    "path": target_file,
                    "has_raw": bool(raw_target_file),
                    "raw_filename": raw_save_name,
                    "raw_path": raw_target_file,
                    "timestamp": self.last_capture_time,
                    "result": result,
                }
            except Exception as e:
                logger.error(f"Native gphoto2 capture error: {e}")
                try:
                    _ = self._camera.get_summary()
                except Exception:
                    logger.warning("Camera connection dropped after capture error")
                    self.is_connected = False
                return {"status": "ERROR", "message": str(e)}

    async def capture_preview_frame(self, gain: float = 1.0) -> bytes:
        """Capture live preview frame bytes from native gPhoto2 camera. Raises on error."""
        if not self.is_connected or not self._camera:
            raise Exception("Camera is disconnected")

        async with self._lock:
            try:
                def _do_preview():
                    camera_file = self._camera.capture_preview()
                    file_data = camera_file.get_data_and_size()
                    return bytes(file_data)

                return await asyncio.to_thread(_do_preview)
            except Exception as e:
                logger.warning(f"Native gphoto2 capture_preview error: {e}")
                raise Exception(f"gphoto2 preview failure: {e}") from e

    def close(self):
        """Close persistent camera session cleanly and reset state."""
        if self._camera:
            try:
                logger.info("Closing persistent python-gphoto2 session...")
                self._camera.exit()
            except Exception as e:
                logger.error(f"Error closing camera session: {e}")
            finally:
                self._camera = None
        self.is_connected = False
        self.model = "Disconnected"
        self.exposure_mode = "Unknown"

    async def reset_usb(self) -> bool:
        """Attempt hardware USB port reset using usbreset utility or sysfs."""
        def _do_reset():
            targets = ["04a9:3272", "Canon"]
            for tgt in targets:
                try:
                    res = subprocess.run(["usbreset", tgt], capture_output=True, text=True, timeout=5)
                    if res.returncode == 0:
                        logger.info(f"Hardware USB reset succeeded for target '{tgt}': {res.stdout.strip()}")
                        return True
                except Exception as e:
                    logger.debug(f"usbreset '{tgt}' exception: {e}")
            return False

        try:
            return await asyncio.to_thread(_do_reset)
        except Exception as e:
            logger.warning(f"Error executing hardware USB reset: {e}")
            return False

    async def restart(self) -> bool:
        """Perform full camera recovery: close session, reset hardware USB port, and re-initialize."""
        if self._is_restarting:
            logger.info("Camera restart already in progress, waiting for it to complete...")
            for _ in range(30):
                if not self._is_restarting:
                    return self.is_connected
                await asyncio.sleep(0.5)
            return self.is_connected

        self._is_restarting = True
        try:
            logger.info("Starting complete camera recovery and restart sequence...")
            self.close()
            await asyncio.sleep(0.5)

            # 1. Hardware USB reset
            usb_reset_ok = await self.reset_usb()
            if usb_reset_ok:
                logger.info("USB bus reset executed. Waiting 2.5s for kernel enumeration...")
                await asyncio.sleep(2.5)
            else:
                logger.info("Proceeding to re-initialize gphoto2 session...")
                await asyncio.sleep(1.0)

            # 2. Re-initialize gphoto2 session
            connected = await self.initialize()
            if connected:
                await self.apply_startup_defaults()
                logger.info(f"Camera restart successful: '{self.model}', mode='{self.exposure_mode}'")
                return True
            else:
                logger.error("Camera restart failed: could not re-establish session.")
                return False
        finally:
            self._is_restarting = False

    async def reconnect(self) -> bool:
        """Alias for restart()."""
        return await self.restart()

    def consume_pending_focus_change(self) -> dict[str, Any]:
        """Consume and summarize all focus commands executed since the prior snapshot."""
        actions = list(self._pending_focus_actions)
        self._pending_focus_actions.clear()
        if not actions:
            return {"actions": [], "summary": "Unchanged", "has_change": False}
        from collections import Counter
        counts = Counter(actions)
        summary = ", ".join(f"{k} (x{v})" if v > 1 else k for k, v in counts.items())
        return {"actions": actions, "summary": summary, "has_change": True}

    def get_status(self) -> dict[str, Any]:
        return {
            "connected": self.is_connected,
            "mock_mode": False,
            "camera_type": "gphoto2",
            "model": self.model,
            "exposure_mode": self.exposure_mode,
            "is_manual_mode": self.is_manual_mode,
            "iso": self.iso,
            "shutter_speed": self.shutter_speed,
            "aperture": self.aperture,
            "white_balance": self.white_balance,
            "image_format": self.image_format,
            "raw_enabled": "RAW" in (self.image_format or "").upper(),
            "has_latest_photo": self.latest_photo_path is not None and os.path.exists(self.latest_photo_path),
            "latest_photo_filename": os.path.basename(self.latest_photo_path) if self.latest_photo_path else None,
            "last_capture_time": self.last_capture_time,
        }
