#!/usr/bin/env bash
# ==============================================================================
# restart_camera.sh - Hardware USB reset and reconnection tool for DSLR
# ==============================================================================

set -euo pipefail

API_URL="${API_URL:-http://localhost:8000}"
CANON_USB_ID="${CANON_USB_ID:-04a9:3272}"

echo "=========================================================="
echo " 📸 CameraCommander Camera Restart Tool"
echo "=========================================================="

# Check if backend is alive and responding
BACKEND_ALIVE=0
if curl -s -m 2 "$API_URL/api/camera/status" >/dev/null 2>&1; then
    BACKEND_ALIVE=1
fi

if [[ "$BACKEND_ALIVE" -eq 1 ]]; then
    echo "Backend detected at $API_URL. Triggering full camera recovery..."
    RESPONSE=$(curl -s -X POST -w "\n%{http_code}" "$API_URL/api/camera/restart")
    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
    BODY=$(echo "$RESPONSE" | sed '$d')

    if [[ "$HTTP_CODE" -eq 200 ]]; then
        echo "✅ Camera successfully restarted and reconnected!"
        echo ""
        echo "$BODY" | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    model = d.get("model", "Unknown")
    exp_mode = d.get("exposure_mode", "Unknown")
    iso = d.get("iso", "Auto")
    shutter = d.get("shutter_speed", "auto")
    aperture = d.get("aperture", "implicit auto")
    is_m = d.get("is_manual_mode", False)

    print("  Model         : %s" % model)
    print("  Exposure Mode : %s" % exp_mode)
    if not is_m:
        print("  ⚠️ WARNING     : Camera dial is NOT set to \"M\" (Manual)!")
        print("                  Exposure settings (ISO/shutter/aperture) are locked by camera.")
        print("                  Please turn the physical dial on top of the camera to \"M\".")
    else:
        print("  Status        : Manual (M) mode verified ✅")
    print("  ISO           : %s" % iso)
    print("  Shutter Speed : %s" % shutter)
    print("  Aperture      : %s" % aperture)
except Exception as e:
    print(d)
'
        exit 0
    else
        echo "⚠️ Backend /api/camera/restart returned HTTP $HTTP_CODE:"
        echo "$BODY"
        echo ""
        echo "Falling back to direct hardware USB reset..."
    fi
fi

# Fallback or standalone hardware USB reset
echo "Performing hardware USB reset on target '$CANON_USB_ID'..."
if command -v usbreset >/dev/null 2>&1; then
    usbreset "$CANON_USB_ID" || usbreset "Canon" || true
else
    echo "Notice: 'usbreset' command not found in PATH."
fi

echo "Waiting 2 seconds for USB bus to re-enumerate..."
sleep 2

if command -v gphoto2 >/dev/null 2>&1; then
    echo "Scanning with gphoto2..."
    gphoto2 --auto-detect || true
fi

echo ""
echo "Hardware reset complete."
if [[ "$BACKEND_ALIVE" -eq 1 ]]; then
    echo "Re-attempting API reconnection..."
    curl -s -X POST "$API_URL/api/camera/reconnect" | python3 -m json.tool || true
fi
