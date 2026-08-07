# Hardware Specification & Wiring Guide (Extracted from Previous Build)

## 1. Controller Board
- **Microcontroller**: NodeMCU v3 (ESP8266 / ESP32 platform)
- **Serial Connection**: USB UART `/dev/ttyUSB0` at **`9600`** baud rate.

## 2. Stepper Motors & Mechanics
- **Base Motor**: NEMA 17 (200 steps per revolution / 1.8° step angle).
- **Default Microstepping**: `16` microsteps (selectable via MS1/MS2/MS3 lines: 1, 2, 4, 8, 16).
- **Gear Ratios**:
  - **Pan Axis (Turntable - TT)**: Gear Ratio = `11.335`
    - Motor steps per output degree = `(200 * 11.335 * microstep) / 360`
  - **Tilt Axis (Vertical - VT)**: Gear Ratio = `6.2 * 7.5` = `46.5`
    - Motor steps per output degree = `(200 * 46.5 * microstep) / 360`

## 3. Pinout Mapping (NodeMCU Pinout)

| Axis / Function | STEP Pin | DIR Pin | ENABLE Pin |
|---|---|---|---|
| **Pan (Turntable - TT)** | `D4` (GPIO2) | `D5` (GPIO14) | `D0` (GPIO16) |
| **Tilt (Vertical - VT)** | `D6` (GPIO12) | `D7` (GPIO13) | `D8` (GPIO15) |

| Microstep Control | Pin |
|---|---|
| `MS1` | `D1` (GPIO5) |
| `MS2` | `D2` (GPIO4) |
| `MS3` | `D3` (GPIO0) |

## 4. Camera Interface
- **Model**: Canon DSLR (USB PTP control).
- **Interface**: Direct USB cable connected to Raspberry Pi Zero 2 W host (`gphoto2` integration).
