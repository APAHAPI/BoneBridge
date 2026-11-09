bl_info = {
    "name": "BoneBridge",
    "author": "BoneBridge contributors",
    "version": (1, 4, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > BoneBridge",
    "description": "Drives the active pose bone rotation from an IMU streamed over serial",
    "category": "Animation",
}

import bpy
import serial
import threading
import math
import time
import serial.tools.list_ports

ser_connection = None
streaming_active = False
serial_thread = None
latest_data = (0.0, 0.0, 0.0)

# Smoothing variables
smoothed_data = [0.0, 0.0, 0.0]
DEFAULT_SMOOTHING = 0.25

# Automatic port detection
DETECT_BAUD = 115200
DETECT_TIMEOUT = 2.5
DETECT_MIN_LINES = 3
DETECT_ENOUGH_LINES = 20
MAX_ANGLE = 720.0

scan_in_progress = False
detected_port = ""

# Stream start behavior
sample_count = 0
reference_data = None
reference_after = 0
capture_reference = False

# Tracking state for automatic axis swapping
_prev_mapping = {'roll': '0', 'pitch': '1', 'yaw': '2'}
_is_updating = False

def update_mapping(self, context):
    global _prev_mapping, _is_updating
    if _is_updating:
        return

    wm = context.window_manager
    curr = {
        'roll': wm.map_roll_from,
        'pitch': wm.map_pitch_from,
        'yaw': wm.map_yaw_from
    }

    changed_key = None
    for k in curr:
        if curr[k] != _prev_mapping[k]:
            changed_key = k
            break

    if changed_key:
        val = curr[changed_key]
        for k in curr:
            if k != changed_key and curr[k] == val:
                curr[k] = _prev_mapping[changed_key]
                break

        _is_updating = True
        wm.map_roll_from = curr['roll']
        wm.map_pitch_from = curr['pitch']
        wm.map_yaw_from = curr['yaw']
        _is_updating = False

    _prev_mapping = curr.copy()

def wrap_degrees(angle):
    return (angle + 180.0) % 360.0 - 180.0

def parse_line(line):
    """Return the three angles on a serial line, or None when it is not a sample."""
    parts = line.split(',')
    if len(parts) < 3:
        return None
    try:
        values = [float(v) for v in parts[:3]]
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in values):
        return None
    return values

def is_sample(line):
    """True when a line looks like the angles a sketch would send."""
    values = parse_line(line)
    if values is None:
        return False
    return all(abs(v) <= MAX_ANGLE for v in values)

def probe_port(device, baud=DETECT_BAUD, timeout=DETECT_TIMEOUT):
    """Count samples on one port. Zero means nothing there speaks BoneBridge."""
    deadline = time.monotonic() + timeout
    connection = None
    good = 0
    try:
        connection = serial.Serial()
        connection.port = device
        connection.baudrate = baud
        connection.timeout = 0.1
        try:
            # Leave the control lines low so opening the port does not reset the board
            connection.dtr = False
            connection.rts = False
        except Exception:
            pass
        while good < DETECT_ENOUGH_LINES and time.monotonic() < deadline:
            try:
                if not connection.is_open:
                    connection.open()
                raw = connection.readline()
            except Exception:
                # A native USB board drops off the bus for a moment when it resets
                time.sleep(0.2)
                continue
            if not raw:
                continue
            if is_sample(raw.decode('utf-8', errors='ignore').strip()):
                good += 1
    finally:
        try:
            if connection is not None and connection.is_open:
                connection.close()
        except Exception:
            pass
    return good

def _probe_worker(device, results):
    results[device] = probe_port(device)

def _scan_worker(devices, results):
    global scan_in_progress, detected_port

    threads = []
    for device in devices:
        thread = threading.Thread(target=_probe_worker, args=(device, results), daemon=True)
        thread.start()
        threads.append(thread)

    # Never let one stuck driver hold the whole scan open
    deadline = time.monotonic() + DETECT_TIMEOUT + 2.0
    for thread in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        thread.join(remaining)

    best_device, best_count = "", 0
    for device in sorted(results):
        if results[device] > best_count:
            best_device, best_count = device, results[device]
    detected_port = best_device if best_count >= DETECT_MIN_LINES else ""
    scan_in_progress = False

def start_port_scan():
    """Probe every serial port at the same time and remember the best one."""
    global scan_in_progress, detected_port

    ports = list(serial.tools.list_ports.comports())
    detected_port = ""
    if not ports:
        scan_in_progress = False
        return False

    results = {p.device: 0 for p in ports}
    scan_in_progress = True
    threading.Thread(target=_scan_worker, args=([p.device for p in ports], results), daemon=True).start()
    return True

def tag_view3d_redraw(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        region.tag_redraw()

def serial_worker(port, baud):
    global ser_connection, latest_data, streaming_active, sample_count
    try:
        ser_connection = serial.Serial(port, baud, timeout=0.1)
        while streaming_active:
            if ser_connection and ser_connection.in_waiting:
                line = ser_connection.readline().decode('utf-8', errors='ignore').strip()
                values = parse_line(line)
                if values is None:
                    continue
                latest_data = tuple(values)
                sample_count += 1
    except Exception as e:
        print(f"Serial error: {e}")
    finally:
        try:
            if ser_connection is not None and hasattr(ser_connection, 'is_open') and ser_connection.is_open:
                ser_connection.close()
        except Exception:
            pass

def get_serial_ports(self, context):
    ports = serial.tools.list_ports.comports()
    items = [("", "Select Port...", "")]
    for p in ports:
        items.append((p.device, p.device, f"{p.description}"))
    if len(ports) == 0:
        items.append(("NONE", "No Ports Found", ""))
    return items

class MPU_OT_StartStream(bpy.types.Operator):
    bl_idname = "object.mpu_start_stream"
    bl_label = "Start BoneBridge Stream"

    baud_rate: bpy.props.IntProperty(name="Baud Rate", default=115200)
    _timer = None
    _state = 'STREAMING'

    def _open_port(self, context, port):
        global streaming_active, serial_thread, ser_connection
        global smoothed_data, reference_data, capture_reference, reference_after

        try:
            if ser_connection is not None and hasattr(ser_connection, 'is_open') and ser_connection.is_open:
                ser_connection.close()
        except Exception:
            pass

        streaming_active = True
        serial_thread = threading.Thread(target=serial_worker, args=(port, self.baud_rate), daemon=True)
        serial_thread.start()

        wm = context.window_manager
        smoothed_data = [0.0, 0.0, 0.0]
        reference_data = None
        reference_after = sample_count
        capture_reference = wm.start_pose_mode == 'REFERENCE'
        self.report({'INFO'}, f"BoneBridge stream started on {port}.")

    def _remove_timer(self, context):
        if self._timer is not None:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except Exception:
                pass
            self._timer = None

    def execute(self, context):
        if streaming_active:
            return {'CANCELLED'}

        wm = context.window_manager
        port = wm.mpu_com_port
        if port and port != "NONE":
            self._state = 'STREAMING'
            self._open_port(context, port)
        else:
            # Nothing selected: find the board before streaming
            if not scan_in_progress and not start_port_scan():
                self.report({'ERROR'}, "No serial ports found. Plug the board in and try again.")
                return {'CANCELLED'}
            self._state = 'SCANNING'

        self._timer = wm.event_timer_add(0.02, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global streaming_active, smoothed_data, capture_reference, reference_data

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        if self._state == 'SCANNING':
            if scan_in_progress:
                return {'PASS_THROUGH'}
            wm = context.window_manager
            self._remove_timer(context)
            if not detected_port:
                self.report({'ERROR'}, "No BoneBridge device found. Select a port by hand, then start again.")
                return {'CANCELLED'}
            try:
                wm.mpu_com_port = detected_port
            except Exception:
                pass
            self._open_port(context, detected_port)
            self._state = 'STREAMING'
            self._timer = wm.event_timer_add(0.02, window=context.window)
            return {'PASS_THROUGH'}

        if not streaming_active:
            self._remove_timer(context)
            return {'FINISHED'}

        bone = context.active_pose_bone
        wm = context.window_manager

        if bone and wm.use_rotation:
            smoothing = max(0.01, min(1.0, wm.smoothing_factor))

            r_idx, r_sign = int(wm.map_roll_from), float(wm.sign_roll)
            p_idx, p_sign = int(wm.map_pitch_from), float(wm.sign_pitch)
            y_idx, y_sign = int(wm.map_yaw_from), float(wm.sign_yaw)

            if capture_reference:
                if sample_count > reference_after:
                    reference_data = latest_data
                    capture_reference = False
                else:
                    # Hold the rest pose until a sample taken after start arrives
                    return {'PASS_THROUGH'}

            incoming = list(latest_data)
            if reference_data is not None:
                incoming = [wrap_degrees(v - r) for v, r in zip(incoming, reference_data)]

            target_roll = incoming[r_idx] * r_sign
            target_pitch = incoming[p_idx] * p_sign
            target_yaw = incoming[y_idx] * y_sign

            smoothed_data[0] += (target_roll - smoothed_data[0]) * smoothing
            smoothed_data[1] += (target_pitch - smoothed_data[1]) * smoothing
            smoothed_data[2] += (target_yaw - smoothed_data[2]) * smoothing

            roll, pitch, yaw = smoothed_data

            bone.rotation_mode = 'XYZ'
            bone.rotation_euler = (
                math.radians(pitch),
                math.radians(roll),
                math.radians(yaw)
            )

        tag_view3d_redraw(context)
        return {'PASS_THROUGH'}

    def cancel(self, context):
        global streaming_active
        streaming_active = False
        self._remove_timer(context)


class MPU_OT_DetectPort(bpy.types.Operator):
    bl_idname = "object.mpu_detect_port"
    bl_label = "Detect BoneBridge Port"
    bl_description = "Scan every serial port and select the one sending BoneBridge samples"

    _timer = None

    def execute(self, context):
        if streaming_active:
            self.report({'WARNING'}, "Stop the stream before scanning ports")
            return {'CANCELLED'}
        if not scan_in_progress and not start_port_scan():
            self.report({'WARNING'}, "No serial ports to scan")
            return {'CANCELLED'}

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        if scan_in_progress:
            return {'PASS_THROUGH'}

        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None

        if detected_port:
            try:
                wm.mpu_com_port = detected_port
            except Exception:
                pass
            self.report({'INFO'}, f"BoneBridge found on {detected_port}")
        else:
            self.report({'WARNING'}, "No BoneBridge device found on any port")
        tag_view3d_redraw(context)
        return {'FINISHED'}

    def cancel(self, context):
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None


class MPU_OT_StopStream(bpy.types.Operator):
    bl_idname = "object.mpu_stop_stream"
    bl_label = "Stop BoneBridge Stream"

    def execute(self, context):
        global streaming_active, ser_connection
        streaming_active = False
        try:
            if ser_connection is not None and hasattr(ser_connection, 'is_open') and ser_connection.is_open:
                ser_connection.close()
        except Exception:
            pass
        self.report({'INFO'}, "BoneBridge stream stopped.")
        return {'FINISHED'}

class MPU_PT_Panel(bpy.types.Panel):
    bl_label = "BoneBridge"
    bl_idname = "VIEW3D_PT_mpu_linker"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "BoneBridge"

    def draw(self, context):
        layout = self.layout
        wm = context.window_manager

        box = layout.box()
        box.label(text="Channels")
        row = box.row(align=True)
        row.prop(wm, "use_rotation", text="Rotation", toggle=True)
        if not wm.use_rotation:
            box.label(text="Rotation is off", icon='ERROR')

        if streaming_active:
            layout.operator("object.mpu_stop_stream", icon='PAUSE', text="Stop Stream")
            layout.label(text="Status: Streaming Active...", icon='REC')
        else:
            row = layout.row(align=True)
            row.prop(wm, "mpu_com_port", text="Port")
            row.operator("object.mpu_detect_port", text="Detect", icon='FILE_REFRESH')
            if scan_in_progress:
                layout.label(text="Scanning ports...", icon='SORTTIME')
            
            box = layout.box()
            box.label(text="Axis & Sign Mapping", icon='ORIENTATION_GLOBAL')
            
            row = box.row(align=True)
            row.prop(wm, "map_roll_from", text="Roll")
            row.prop(wm, "sign_roll", text="")
            
            row = box.row(align=True)
            row.prop(wm, "map_pitch_from", text="Pitch")
            row.prop(wm, "sign_pitch", text="")
            
            row = box.row(align=True)
            row.prop(wm, "map_yaw_from", text="Yaw")
            row.prop(wm, "sign_yaw", text="")

            box = layout.box()
            box.label(text="Start Behavior", icon='POSE_HLT')
            box.prop(wm, "start_pose_mode", expand=True)

            if wm.mpu_com_port and wm.mpu_com_port != "NONE":
                layout.operator("object.mpu_start_stream", icon='PLAY', text="Start Stream")
            else:
                layout.operator("object.mpu_start_stream", icon='PLAY', text="Start Stream (Auto Port)")
            layout.label(text="Status: Ready", icon='INFO')

        box = layout.box()
        box.label(text="Smoothing", icon='SMOOTHCURVE')
        box.prop(wm, "smoothing_factor", text="Factor", slider=False)

axis_items = [('0', 'Roll', ''), ('1', 'Pitch', ''), ('2', 'Yaw', '')]
start_mode_items = [
    ('REFERENCE', 'IMU Initial Pose', 'Capture IMU orientation at start'),
    ('DIRECT', 'IMU Data Directly', 'Apply raw incoming angles straight to bone'),
]
sign_items = [('1', '+', ''), ('-1', '-', '')]

classes = [MPU_OT_StartStream, MPU_OT_StopStream, MPU_OT_DetectPort, MPU_PT_Panel]

def register():
    bpy.types.WindowManager.smoothing_factor = bpy.props.FloatProperty(
        name="Smoothing Factor",
        description="Smoothing level",
        default=DEFAULT_SMOOTHING,
        min=0.01,
        max=1.0,
        precision=2
    )
    bpy.types.WindowManager.use_rotation = bpy.props.BoolProperty(
        name="Rotation",
        description="Drive bone rotation",
        default=True
    )
    bpy.types.WindowManager.start_pose_mode = bpy.props.EnumProperty(
        name="Start Behavior",
        items=start_mode_items,
        default='DIRECT'
    )
    bpy.types.WindowManager.mpu_com_port = bpy.props.EnumProperty(
        name="Port",
        description="Serial port to stream from; leave it empty to detect the board on start",
        items=get_serial_ports
    )
    bpy.types.WindowManager.map_roll_from = bpy.props.EnumProperty(name="Map Roll", items=axis_items, default='0', update=update_mapping)
    bpy.types.WindowManager.sign_roll = bpy.props.EnumProperty(name="Sign Roll", items=sign_items, default='1')
    
    bpy.types.WindowManager.map_pitch_from = bpy.props.EnumProperty(name="Map Pitch", items=axis_items, default='1', update=update_mapping)
    bpy.types.WindowManager.sign_pitch = bpy.props.EnumProperty(name="Sign Pitch", items=sign_items, default='1')
    
    bpy.types.WindowManager.map_yaw_from = bpy.props.EnumProperty(name="Map Yaw", items=axis_items, default='2', update=update_mapping)
    bpy.types.WindowManager.sign_yaw = bpy.props.EnumProperty(name="Sign Yaw", items=sign_items, default='1')

    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    global streaming_active, ser_connection
    streaming_active = False
    try:
        if ser_connection is not None and hasattr(ser_connection, 'is_open') and ser_connection.is_open:
            ser_connection.close()
    except Exception:
        pass
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.WindowManager.smoothing_factor
    del bpy.types.WindowManager.use_rotation
    del bpy.types.WindowManager.start_pose_mode
    del bpy.types.WindowManager.mpu_com_port
    del bpy.types.WindowManager.map_roll_from
    del bpy.types.WindowManager.sign_roll
    del bpy.types.WindowManager.map_pitch_from
    del bpy.types.WindowManager.sign_pitch
    del bpy.types.WindowManager.map_yaw_from
    del bpy.types.WindowManager.sign_yaw

if __name__ == "__main__":
    register()