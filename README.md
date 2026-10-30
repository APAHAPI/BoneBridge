# BoneBridge

**Drive Blender bones with real IMU hardware.**

BoneBridge is a Blender 4.x add-on that reads orientation from an IMU over a serial port and writes it to the active pose bone. It is deliberately hardware agnostic: the add-on understands a line format, not a specific board. This repo also includes reference firmware for a few setups, so the whole path from sensor to bone works out of the box.

## Scope

The goal is any IMU over any microcontroller, not only the two setups that ship here.

The serial line is the contract: `roll,pitch,yaw` in degrees at **115200 baud**. The add-on never talks to the sensor directly, so the board, sensor and bus are interchangeable. The bundled ESP32-S3 sketches are reference implementations to copy and adapt, not a hardware limit. If your board can read an IMU and print that line, it works with BoneBridge.

The included sketches use I2C because it is the simplest way to wire a breakout. SPI support is planned for sensors that support it; see the roadmap.

## How it works

```
 IMU ── I2C ──▶ microcontroller firmware ──▶ USB serial 115200 ──▶ Blender add-on
                                                   "roll,pitch,yaw"
```

1. **Firmware** reads the IMU over I2C, converts the reading to degrees, and prints one line per sample: `roll,pitch,yaw`, three comma-separated floats with no labels. The BNO085 sketch uses the chip's fused *game rotation vector* quaternion. The MPU6050 sketch derives roll and pitch from the accelerometer and reports yaw as `0`.
2. **The add-on** opens the selected port on a background thread and keeps only the latest valid sample, so Blender never blocks on `readline()`. Lines that do not split into three comma-separated floats, such as startup banners and debug logs, are skipped.
3. **A modal timer** fires every 20 ms, picks up the newest sample, applies the axis remap and sign flips, runs an exponential smoothing pass, then writes the result to the active pose bone's XYZ Euler rotation.
4. **Bone axes are not sensor axes.** The bone receives `(pitch, roll, yaw)` in radians: sensor roll drives the bone's local Y, pitch drives X. Local bone axes depend on how the armature was built, so the panel gives each bone rotation a source channel and a sign flip. Use those controls to align the motion in Blender instead of editing the sketch.

### The serial protocol is the extension point

The add-on does not know what board is on the other end. Any device that prints `<roll>,<pitch>,<yaw>\n` in degrees at **115200 baud** works: an Arduino Uno, a classic ESP32, a Raspberry Pi Pico, a Teensy. Adding a board means adding a sketch, not touching Python.

## Bundled firmware

| Sensor | Board | Bus | Firmware | Status |
| --- | --- | --- | --- | --- |
| BNO085 | ESP32-S3 | I2C | [`firmware/esp32s3_bno085`](firmware/esp32s3_bno085) | Working |
| MPU6050 | ESP32-S3 | I2C | [`firmware/esp32s3_mpu6050`](<firmware/esp32s3_mpu6050 (not tested)>) | Untested |

These are the sketches included in this repo, not a list of supported hardware. Adding another sensor or board is a firmware change; the Blender side stays the same. ESP32-S3 is used here because the boards are cheap, have native USB, and are well supported by the Arduino core. BNO085 and MPU6050 cover the common first builds: fused orientation and a low-cost accelerometer.

## Setup

### 1. Install `pyserial` into Blender's Python

Blender's bundled Python does not include `pyserial`. Install it into Blender's own Python, not into a system Python. This works with the blender.org installer, the Microsoft Store version, Steam, and portable builds, with no install path to look up.

1. Open Blender, switch to the **Scripting** workspace, and open the **Python Console**.
2. Paste this and press Enter:

```python
import bpy, subprocess, sys

target = bpy.utils.user_resource('SCRIPTS', path='modules', create=True)
subprocess.check_call([
    sys.executable, '-m', 'pip', 'install', '--upgrade', '--target', target, 'pyserial'
])
```

The snippet asks Blender where its Python lives, then installs `pyserial` into Blender's user scripts `modules` folder. That folder is writable even when Blender itself is installed in a protected location such as `C:\Program Files\WindowsApps`.

3. Restart Blender, open the Python Console again, and confirm the install:

```python
import serial; print(serial.__version__)
```

If that prints a version number, you are done.

### 2. Install the add-on

Edit → Preferences → Add-ons → dropdown (top right) → **Install from Disk…** → choose `addon/bonebridge.py` → enable **BoneBridge**.

Blender 4.2+ loads single-file legacy add-ons this way; the add-on does not need to be an Extension.

The panel appears in the 3D Viewport sidebar (`N`) as the **BoneBridge** tab.

### 3. Flash the firmware

The bundled sketches target ESP32-S3. For another board the flow is the same: install its board core, install a library for the sensor, copy the matching sketch, set the pins, then confirm it prints three comma-separated numbers at 115200.

Arduino IDE 2.x for the bundled sketches:

1. **Boards Manager** → install *esp32* by Espressif Systems.
2. **Library Manager** → install *Adafruit BNO08x* and *Adafruit BusIO* for the BNO085 sketch, or *MPU6050* by Electronic Cats for the MPU6050 sketch.
3. Open the matching sketch from `firmware/`.
4. Select board **ESP32S3 Dev Module** and your port.
5. Set **USB CDC On Boot: Enabled**. Without it, `Serial` does not reach the S3's native USB and Blender reads nothing.
6. Upload.

Wiring is in the comment block at the top of each sketch, and the matching `.txt` copy has the same notes. Change `SDA_PIN` and `SCL_PIN` there if your board uses different pins.

Both sketches stream at 115200 baud, which is what the add-on expects.

## Using it

1. Put the armature in **Pose Mode** and select the bone to drive. The add-on writes to the *active pose bone*, so a bone must be selected in Pose Mode, not Object Mode.
2. Open the sidebar (`N`) → **BoneBridge**.
3. Pick a port. The dropdown is rebuilt from the ports the OS reports each time the panel draws.
4. Optional: under **Axis & Sign Mapping**, choose which incoming channel feeds each bone rotation and flip any axis. Selecting a channel that is already in use swaps the two rather than duplicating it.
5. **Start Stream**. **Stop Stream** ends the session; starting again re-reads the port list.

Smoothing is the `SMOOTHING_FACTOR` constant at the top of `bonebridge.py` (default `0.25`): lower is smoother but laggier, higher is snappier but noisier. Mounting matters more than filtering. A sensor taped loosely to a prop will shimmy no matter what.

Streaming only sets the live pose; nothing is keyed. Turn on **Auto Key** and play the timeline to capture a take.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| "No Ports Found" | Charge-only USB cable, or missing driver. Many ESP32-S3 boards need CP210x or CH340 drivers. |
| `Serial error: could not open port ...` | The port is held by another program, usually the Arduino Serial Monitor or Plotter. Close it. |
| `ModuleNotFoundError: No module named 'serial'` | Step 1 was skipped or `pyserial` went into another Python. Re-run the snippet in Blender's Python Console, then restart Blender. |
| `import serial` works in a terminal but not in Blender | `pyserial` was installed into the system Python. Install it into Blender's Python with step 1. |
| Port listed, nothing moves | `USB CDC On Boot` is disabled, or it is the wrong port. Open the Serial Monitor at 115200 to see whether numbers arrive, then close it. |
| Bone never moves | Armature is not in Pose Mode, or no bone is selected. |
| Wrong axes / mirrored motion | Fix it with Axis & Sign Mapping. |
| Jittery motion | Mount the sensor rigidly, lower `SMOOTHING_FACTOR`, or raise the sketch's `delay(20)` for a lower sample rate. |
| MPU6050 yaw stuck at 0 | Expected. The sketch has no magnetometer. |

## Roadmap

- [x] ESP32-S3 + BNO085
- [x] ESP32-S3 + MPU6050
- [x] Axis remapping with per-axis sign flips
- [ ] SPI support alongside I2C, starting with the BNO085
- [ ] Arduino Uno / Nano firmware (MPU6050 over I2C)
- [ ] ESP32 classic, C3 and S2 builds
- [ ] MPU9250 with magnetometer-based yaw
- [ ] Quaternion transport (no gimbal lock)
- [ ] Multiple boards / multiple bones at once
- [ ] Bake the live stream to keyframes
- [ ] Smoothing, baud rate and sensor address exposed in the panel

## Contributing

New firmware is the most useful contribution: add a `firmware/<board>_<sensor>/` sketch that prints `roll,pitch,yaw` at 115200 baud and opens with its wiring in a comment block. Bug reports and Blender-side fixes are welcome too.

## License

MIT. See [LICENSE](LICENSE).
