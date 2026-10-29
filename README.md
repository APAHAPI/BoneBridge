# BoneBridge

**Drive Blender bones with real IMU hardware.**

BoneBridge is a Blender 4.x add-on that listens to an IMU streaming over USB serial and writes its orientation straight onto the active pose bone. This repo ships the matching firmware if available, so it works end to end: wire an IMU to a board, flash the sketch, pick the port in Blender, tilt and move the sensor and the bone follows.

## How it works

```
 IMU ── I2C/SPI ──▶ microcontroller firmware ──▶ USB serial 115200 ──▶ Blender add-on
                                                   "roll,pitch,yaw"
```

1. **Firmware** reads the IMU over I2C/SPI, converts the reading to degrees, and prints one line per sample: `roll,pitch,yaw` three comma-separated floats, no labels. The BNO085 sketch uses the chip's fused *game rotation vector* quaternion; the MPU6050 sketch derives roll and pitch from the accelerometer.
2. **The add-on** opens the selected port on a background thread and keeps only the latest valid sample, so Blender never blocks on `readline()`. Lines that don't split into three comma-separated values: startup banners and debug logs are skipped.
3. **A modal timer** fires every 20 ms, picks up the newest sample, applies the axis remap and sign flips, runs an exponential smoothing pass, then writes the result to the active pose bone's XYZ Euler rotation.
4. **Bone axes are not sensor axes.** The bone receives `(pitch, roll, yaw)` in radians: sensor roll drives the bone's local Y, pitch drives X. Local bone axes depend on how the armature was built, which is why the panel exposes a source channel and a sign flip per axis, you realign in the panel instead of patching the sketch to avoid losing time.

### The serial protocol is the extension point

The add-on doesn't know what board is on the other end. Any device that prints `<roll>,<pitch>,<yaw>\n` in degrees at **115200 baud** works: an Arduino Uno, a classic ESP32, a Raspberry Pi Pico. Adding a board means adding a sketch, not touching Python.

## Supported hardware

| Sensor | Board | Firmware | Status |
| --- | --- | --- | --- |
| BNO085 | ESP32-S3 | [`firmware/esp32s3_bno085`](firmware/esp32s3_bno085) | Working |
| MPU6050 | ESP32-S3 | [`firmware/esp32s3_mpu6050`](firmware/esp32s3_mpu6050) | Testing |
| MPU9250 | ESP32-S3 | — | Planned |
| MPU6050 | Arduino Uno / Nano | — | Planned |
| BNO085 | ESP32 classic / C3 | — | Planned |

More coming in the future

## Setup

### 1. Install `pyserial` into Blender's Python

Blender's bundled interpreter doesn't ship `pyserial`. Install it there, not into your system Python. Match the version folder (`4.2`, `4.3`, `4.4` …) to your Blender build.

Windows:

```
"C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe" -m pip install pyserial
```

macOS:

```
/Applications/Blender.app/Contents/Resources/4.2/python/bin/python3.11 -m pip install pyserial
```

Linux (blender.org tarball):

```
~/blender-4.2.0-linux-x64/4.2/python/bin/python3.11 -m pip install pyserial
```

Confirm in Blender's Scripting workspace → Python Console:

```python
import serial; print(serial.__version__)
```

### 2. Install the add-on

Edit → Preferences → Add-ons → dropdown (top right) → **Install from Disk…** → choose `addon/bonebridge.py` → enable **BoneBridge**.

Blender 4.2+ loads single-file legacy add-ons this way; the add-on does not need to be an Extension.

The panel appears in the 3D Viewport sidebar (`N`) as the **BoneBridge** tab.

### 3. Flash the firmware

Arduino IDE 2.x:

1. **Boards Manager** → install *esp32* by Espressif Systems.
2. **Library Manager** → install *Adafruit BNO08x* and *Adafruit BusIO* for the BNO085 sketch, or *MPU6050* by Electronic Cats for the MPU6050 sketch.
3. Open the matching sketch from `firmware/`.
4. Select board **ESP32S3 Dev Module** and your port.
5. Set **USB CDC On Boot: Enabled** — without it `Serial` goes nowhere on the S3's native USB and Blender will read zeros.
6. Upload.

Both sketches stream at 115200 baud, which is what the add-on expects.

## Wiring

Different board layout? Change `SDA_PIN` and `SCL_PIN` at the top of the sketch. Both sensors are usually at I2C address `0x4A` (BNO085) and `0x68` (MPU6050); the `PS0`/`PS1` and `AD0` pins change that.

## Using it

1. Put the armature in **Pose Mode** and select the bone to drive. The add-on writes to the *active pose bone*, so a bone must be selected in Pose Mode — not Object Mode.
2. Open the sidebar (`N`) → **BoneBridge**.
3. Pick a port. The dropdown is rebuilt from the ports the OS reports each time the panel draws.
4. Optional: under **Axis & Sign Mapping**, choose which incoming channel feeds each bone rotation and flip any axis. Selecting a channel that's already in use swaps the two rather than duplicating it.
5. **Start Stream**. **Stop Stream** ends the session; starting again re-reads the port list.

Smoothing is the `SMOOTHING_FACTOR` constant at the top of `bonebridge.py` (default `0.25`): lower is smoother but laggier, higher is snappier but noisier. Mounting matters more than filtering — a sensor taped loosely to a prop will shimmy no matter what.

Streaming only sets the live pose; nothing is keyed. Turn on **Auto Key** and play the timeline to capture a take.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| "No Ports Found" | Charge-only USB cable, or missing driver. Many ESP32-S3 boards need CP210x or CH340 drivers. |
| `Serial error: could not open port …` | The port is held by another program — usually the Arduino Serial Monitor or Plotter. Close it. |
| `ModuleNotFoundError: No module named 'serial'` | Step 1 was skipped, or installed into the wrong Python. Install into *Blender's* interpreter. |
| Port listed, nothing moves | `USB CDC On Boot` is disabled, or it's the wrong port. Open the Serial Monitor at 115200 to see whether numbers arrive, then close it. |
| Bone never moves | Armature isn't in Pose Mode, or no bone is selected. |
| Wrong axes / mirrored motion | Fix it with Axis & Sign Mapping. |
| Jittery motion | Mount the sensor rigidly, lower `SMOOTHING_FACTOR`, or raise the sketch's `delay(20)` for a lower sample rate. |
| MPU6050 yaw stuck at 0 | Expected — the sketch has no magnetometer. |

## Roadmap

- [x] ESP32-S3 + BNO085
- [x] ESP32-S3 + MPU6050
- [x] Axis remapping with per-axis sign flips
- [ ] Arduino Uno / Nano firmware (MPU6050 over I2C)
- [ ] ESP32 classic, C3 and S2 builds
- [ ] MPU9250 with magnetometer-based yaw
- [ ] Quaternion transport (no gimbal lock)
- [ ] Multiple boards / multiple bones at once
- [ ] Bake the live stream to keyframes
- [ ] Smoothing, baud rate and sensor address exposed in the panel

Contributions are welcome, especially new `firmware/<board>_<sensor>/` sketches that follow the serial protocol above.

## License

MIT — see [LICENSE](LICENSE).
