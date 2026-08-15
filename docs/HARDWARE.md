# pantiltlapse-rig Hardware Reference

Default PlatformIO target: NodeMCU v3 / ESP8266 (`nodemcuv2`), USB serial 9600 baud.

| Function | Pins |
|---|---|
| Pan STEP / DIR / ENABLE | D4/GPIO2, D5/GPIO14, D0/GPIO16 |
| Tilt STEP / DIR / ENABLE | D6/GPIO12, D7/GPIO13, D8/GPIO15 |
| Shared MS1 / MS2 / MS3 | D1/GPIO5, D2/GPIO4, D3/GPIO0 |

Enable is active-low. Both axes therefore share one microstep setting (default 16). `esp32dev` is listed in `platformio.ini`, but the source uses NodeMCU `D0`–`D8` aliases: replace and validate the map before targeting a generic ESP32.

| Axis | Motor | Gear ratio | Output full steps/rev | 16× microsteps/degree |
|---|---|---:|---:|---:|
| Pan | NEMA 17, 200 steps/rev | 11.335 | 2,267 | ~100.76 |
| Tilt | NEMA 17, 200 steps/rev | 46.5 (`6.2 × 7.5`) | 9,300 | ~413.33 |

Pan is inverted so positive means right. There are no endstops, homing, persisted position, or travel-limit checks; boot and driver toggles set both coordinates to zero. Establish a safe zero manually, stay within mechanical limits, and use an external motor-power cutoff: `X` cannot interrupt a synchronous `M` move.

Connect a supported Canon DSLR by USB PTP; the backend uses persistent `python-gphoto2`. Without hardware, set `FAKE_CAMERA=true` in `backend/.env`.

```bash
cd firmware
pio run
pio run --target upload
pio device monitor --baud 9600
```
