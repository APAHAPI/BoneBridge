# BoneBridge

**Drive Blender bones with a BNO085 over serial.**

BoneBridge is a Blender 4.x add-on that reads orientation from an IMU over a serial port and writes it to the active pose bone. This repo maintains one setup: a BNO085 on an ESP32-S3, over I2C or SPI. The add-on itself only understands the serial line, so a different board can be made to work by adapting the sketch.

## Scope

BNO085 on an ESP32-S3 is the reference setup and the only one this repo maintains. There are no plans to add other sensors or boards; the two sketches in `firmware/` are examples to adapt, not a supported hardware list.

The serial line is the contract: `roll,pitch,yaw` in degrees at **115200 baud**, with an optional `,ax,ay,az` suffix for linear acceleration. Anything that prints that line drives the bone. If your hardware is different, read [You have a different board?](#you-have-a-different-board).

## How it works

```
 BNO085  (I2C or SPI) ──▶ ESP32-S3 firmware ──▶ USB serial 115200 ──▶ Blender add-on
                                                          "roll,pitch,yaw"
```

1. **Firmware** reads the BNO085, converts the fused rotation vector to degrees, and prints one line per sample: `roll,pitch,yaw`, three comma-separated floats with no labels.
2. **The add-on** opens the port on a background thread and keeps only the latest valid sample, so Blender never blocks on `readline()`. Lines that do not split into at least three comma-separated floats, such as startup banners and debug logs, are skipped.
3. **A modal timer** fires every 20 ms while the **Rotation** channel is on, picks up the newest sample, optionally subtracts the orientation captured at stream start, applies the axis remap and sign flips, runs an exponential smoothing pass at the rate set in the panel, then writes the result to the active pose bone's XYZ Euler rotation.
4. **Bone axes are not sensor axes.** The bone receives `(pitch, roll, yaw)` in radians: sensor roll drives the bone's local Y, pitch drives X. Local bone axes depend on how the armature was built, so the panel gives each bone rotation a source channel and a sign flip. Use those controls to align the motion in Blender instead of editing the sketch.
5. **The port is found by listening.** When no port is selected, the add-on opens every serial port at once for a couple of seconds and picks the one that is sending lines shaped like `roll,pitch,yaw`. Compared with guessing from port names, that keeps working when the board gets a new COM number.

## Bundled firmware

| Sensor | Board | Bus | Firmware | Sends |
| --- | --- | --- | --- | --- |
<<<<<<< HEAD
| BNO085 | ESP32-S3 | I2C | [`firmware/I2C/esp32s3_bno085_I2C`](firmware/I2C/esp32s3_bno085_I2C) | `roll,pitch,yaw` |
| BNO085 | ESP32-S3 | SPI | [`firmware/SPI/esp32s3_bno085_SPI`](firmware/SPI/esp32s3_bno085_SPI) | `roll,pitch,yaw` |
=======
| BNO085 | ESP32-S3 | I2C | [`firmware/esp32s3_bno085`](firmware/esp32s3_bno085) | Fully Working |
| MPU6050 | ESP32-S3 | I2C | [`firmware/esp32s3_mpu6050`](<firmware/esp32s3_mpu6050 (not tested)>) | Working only on 2 axis |
>>>>>>> 1c419d6c4bbeefeebad3174735a0fb5e7a01333d

Both print a startup banner that the add-on skips.

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

<<<<<<< HEAD
Edit → Preferences → Add-ons → dropdown (top right) → **Install from Disk…** → choose `addon/bone_bridge.zip` → enable **BoneBridge**.
=======
Edit → Preferences → Add-ons → dropdown (top right) → **Install from Disk…** → choose `addon/bonebridge.zip` → enable **BoneBridge**.
>>>>>>> 1c419d6c4bbeefeebad3174735a0fb5e7a01333d

The zip is a Blender 4.2+ extension. The readable source lives in `addon/bone_bridge/` if you want to read or change it.

The panel appears in the 3D Viewport sidebar (`N`) as the **BoneBridge** tab.

### 3. Flash the firmware

Both sketches target an ESP32-S3 and a BNO085. Arduino IDE 2.x:

1. **Boards Manager** → install *esp32* by Espressif Systems.
2. **Library Manager** → install *Adafruit BNO08x* and *Adafruit BusIO*.
3. Open the sketch for your wiring, from `firmware/I2C/` or `firmware/SPI/`.
4. Select board **ESP32S3 Dev Module** and your port.
5. Set **USB CDC On Boot: Enabled**. Without it, `Serial` does not reach the S3's native USB and Blender reads nothing.
6. Upload.

Pins are constants at the top of each sketch, so change them there if your board is wired differently.

Both sketches stream at 115200 baud, which is what the add-on expects.

## Using it

1. Put the armature in **Pose Mode** and select the bone to drive. The add-on writes to the *active pose bone*, so a bone must be selected in Pose Mode, not Object Mode.
2. Open the sidebar (`N`) → **BoneBridge**.
3. Leave **Port** on *Select Port...* to let the add-on find the board, or pick a port yourself if you have several devices attached. **Detect** scans the ports and fills in the dropdown without starting a stream, and the status line reports the scan while it runs.
4. Optional: under **Axis & Sign Mapping**, choose which incoming channel feeds each bone rotation and flip any axis. Selecting a channel that is already in use swaps the two rather than duplicating it.
5. Optional: drag the **Smoothing** factor left or right, or click it to type a value. It runs from `0.01` (very smooth, very laggy) to `1.00` (no smoothing) and starts at `0.25`. The box stays visible while streaming, so you can tune it against the motion you see.
6. Choose what happens at the start of a stream, under **Start Behavior**:
   - **IMU Initial Pose**: the orientation the IMU has at that moment becomes zero. The bone holds its rest pose and only the movement since then is applied, so you can point the sensor where the rest pose should be and then press start.
   - **IMU Data Directly**: the angles the firmware sends are written straight to the bone. The bone jumps to the sensor's absolute orientation as soon as data arrives, and smoothing eases the jump instead of removing it.
7. **Start Stream**. With no port selected the button reads **Start Stream (Auto Port)**: it scans first, picks the board, and starts on it. **Stop Stream** ends the session; starting again re-reads the port list.

The scan opens every port, and opening a port can reset an ESP32. That is expected: the scan keeps reading until the board comes back and starts sending.

Smoothing is an exponential filter: each frame moves the bone part of the way to the newest reading instead of snapping to it. Lower is smoother but laggier, higher is snappier but noisier. Filter state is cleared when a stream starts, so every take begins from rest. Mounting matters more than filtering. A sensor taped loosely to a prop will shimmy no matter what.

Start Behavior is read when you press **Start Stream**, so pick it before starting. In *IMU Initial Pose* mode the offset is taken from the first sample that arrives after start, not from the pose the bone already had, and the bone holds still until that sample lands.

While a stream runs, the panel shows the acceleration in m/s^2 if the sketch sends it and the Acceleration channel is on. That is a readout only; the add-on rotates the bone and leaves its location alone.

Streaming only sets the live pose; nothing is keyed. Turn on **Auto Key** and play the timeline to capture a take.

## You have a different board?

This repo keeps one example and does not plan expansions to other IMUs, MPUs or boards. Adapting it is still possible, because the only thing the add-on cares about is the printed line. The firmware is the part that changes; the Blender side stays as it is.

The fastest route is to have an AI coding agent write the sketch for you. Copy the prompt below, replace the bracketed parts, and paste it in. Attaching the sensor datasheet or the library name helps if the agent does not know the chip.

```text
Write an Arduino sketch that streams orientation from a [SENSOR MODEL] on a [MICROCONTROLLER BOARD] over serial for the BoneBridge Blender add-on.

The add-on expects exactly this protocol:
- 115200 baud, one sample per line, no headers, labels or debug text on the data lines.
- Each line is roll,pitch,yaw in degrees, as three comma-separated floats, for example 12.40,-3.10,178.02.

Requirements:
- Use the sensor's own fused orientation (quaternion or Euler). Do not integrate gyro data by hand and do not derive yaw from an accelerometer.
- Read the sensor over [I2C or SPI] with the [LIBRARY NAME] library.
- Print continuously from loop() without blocking, and never print anything else while streaming.
- Wait for the serial port before streaming, and if the sensor does not answer, print a plain-text error and stop instead of sending zeros.
- Put the wiring for the [MICROCONTROLLER BOARD] at the top of the file as a comment block, and keep every pin in a named constant.
- If the board is an ESP32-S3, remind me to enable USB CDC On Boot in the Arduino IDE.

Return the complete .ino file, ready to paste into the Arduino IDE.
```

Whatever the agent writes, check it in the Serial Monitor at 115200 first: you should see plain lines of numbers and nothing else. Close the monitor before starting a stream, because only one program can hold the port.

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| "No Ports Found" | Charge-only USB cable, or missing driver. Many ESP32-S3 boards need CP210x or CH340 drivers. |
| `Serial error: could not open port ...` | The port is held by another program, usually the Arduino Serial Monitor or Plotter. Close it. |
| "No BoneBridge device found" | Nothing on any port is sending sample lines. Check the Serial Monitor, confirm the **USB CDC On Boot** setting, and make sure the sketch prints bare comma-separated numbers with no labels. |
| `ModuleNotFoundError: No module named 'serial'` | Step 1 was skipped or `pyserial` went into another Python. Re-run the snippet in Blender's Python Console, then restart Blender. |
| `import serial` works in a terminal but not in Blender | `pyserial` was installed into the system Python. Install it into Blender's Python with step 1. |
| Port listed, nothing moves | `USB CDC On Boot` is disabled, or it is the wrong port. Open the Serial Monitor at 115200 to see whether numbers arrive, then close it. |
| Bone never moves | Armature is not in Pose Mode, no bone is selected, or the **Rotation** channel is off. |
| Wrong axes / mirrored motion | Fix it with Axis & Sign Mapping. |
| Bone stays at rest while the sensor moves | **Start Behavior** is on *IMU Initial Pose* and the IMU has barely moved since start. The offset is taken from the first sample after start, so keep the sensor still in the rest pose for a moment, or use *IMU Data Directly*. |
| Jittery motion | Mount the sensor rigidly, lower the **Smoothing** factor, or add a `delay(20)` to the sketch's loop for a lower sample rate. |
| No acceleration readout while streaming | The sketch on the board sends three fields. Flash the I2C sketch from `firmware/I2C/esp32s3_bno085_I2C` to get the readout, or leave it hidden. |

## Roadmap

- [x] BNO085 on ESP32-S3 over I2C
- [x] BNO085 on ESP32-S3 over SPI
- [x] Automatic port detection
- [x] Axis remapping with per-axis sign flips
<<<<<<< HEAD
- [x] Smoothing exposed in the panel
- [x] Start Behavior: IMU initial pose or direct data
=======
- [ ] SPI support
- [ ] Arduino Uno
- [ ] MPU9250 with magnetometer-based yaw
>>>>>>> 1c419d6c4bbeefeebad3174735a0fb5e7a01333d
- [ ] Quaternion transport (no gimbal lock)
- [ ] Multiple boards / multiple bones at once
- [ ] Bake the live stream to keyframes
- [ ] Baud rate and sensor address exposed in the panel

## Contributing

Firmware for other sensors and boards is not planned here. Bug reports and Blender-side fixes are welcome, and if you adapt the serial line to your own hardware, keep it in your fork.

## License

MIT. See [LICENSE](LICENSE).