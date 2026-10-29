bl_info = {
    "name": "BoneBridge",
    "author": "BoneBridge contributors",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > BoneBridge",
    "description": "Drives the active pose bone with roll/pitch/yaw streamed from an IMU over serial",
    "category": "Animation",
}

import bpy
import serial
import threading
import math
import serial.tools.list_ports

ser_connection = None
streaming_active = False
serial_thread = None
latest_data = (0.0, 0.0, 0.0)

# Smoothing variables
smoothed_data = [0.0, 0.0, 0.0]
SMOOTHING_FACTOR = 0.25  # Lower = smoother/slower, Higher = more responsive

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

def serial_worker(port, baud):
    global ser_connection, latest_data, streaming_active
    try:
        ser_connection = serial.Serial(port, baud, timeout=0.1)
        while streaming_active:
            if ser_connection and ser_connection.in_waiting:
                line = ser_connection.readline().decode('utf-8', errors='ignore').strip()
                parts = line.split(',')
                if len(parts) == 3:
                    latest_data = (float(parts[0]), float(parts[1]), float(parts[2]))
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

    def execute(self, context):
        global streaming_active, serial_thread, ser_connection
        
        port = context.window_manager.mpu_com_port
        if not port or port == "NONE":
            self.report({'ERROR'}, "Please select a valid serial port first!")
            return {'CANCELLED'}

        if streaming_active:
            return {'CANCELLED'}

        try:
            if ser_connection is not None and hasattr(ser_connection, 'is_open') and ser_connection.is_open:
                ser_connection.close()
        except Exception:
            pass

        streaming_active = True
        serial_thread = threading.Thread(target=serial_worker, args=(port, self.baud_rate), daemon=True)
        serial_thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.02, window=context.window)
        wm.modal_handler_add(self)
        
        self.report({'INFO'}, f"BoneBridge stream started on {port}.")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global streaming_active, smoothed_data
        if not streaming_active:
            return {'FINISHED'}

        if event.type == 'TIMER':
            bone = context.active_pose_bone
            if bone:
                wm = context.window_manager
                raw_roll, raw_pitch, raw_yaw = latest_data
                incoming = [raw_roll, raw_pitch, raw_yaw]

                r_idx, r_sign = int(wm.map_roll_from), float(wm.sign_roll)
                p_idx, p_sign = int(wm.map_pitch_from), float(wm.sign_pitch)
                y_idx, y_sign = int(wm.map_yaw_from), float(wm.sign_yaw)

                target_roll = incoming[r_idx] * r_sign
                target_pitch = incoming[p_idx] * p_sign
                target_yaw = incoming[y_idx] * y_sign
                
                smoothed_data[0] += (target_roll - smoothed_data[0]) * SMOOTHING_FACTOR
                smoothed_data[1] += (target_pitch - smoothed_data[1]) * SMOOTHING_FACTOR
                smoothed_data[2] += (target_yaw - smoothed_data[2]) * SMOOTHING_FACTOR
                
                roll, pitch, yaw = smoothed_data
                
                bone.rotation_mode = 'XYZ'
                bone.rotation_euler = (
                    math.radians(pitch),
                    math.radians(roll),
                    math.radians(yaw)
                )
                
                for window in context.window_manager.windows:
                    for area in window.screen.areas:
                        if area.type == 'VIEW_3D':
                            for region in area.regions:
                                if region.type == 'WINDOW':
                                    region.tag_redraw()

        return {'PASS_THROUGH'}

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
        
        if streaming_active:
            layout.operator("object.mpu_stop_stream", icon='PAUSE', text="Stop Stream")
            layout.label(text="Status: Streaming Active...", icon='REC')
        else:
            layout.prop(wm, "mpu_com_port", text="Port")
            
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

            layout.operator("object.mpu_start_stream", icon='PLAY', text="Start Stream")
            layout.label(text="Status: Ready", icon='INFO')

axis_items = [('0', 'Roll', ''), ('1', 'Pitch', ''), ('2', 'Yaw', '')]
sign_items = [('1', '+', ''), ('-1', '-', '')]

classes = [MPU_OT_StartStream, MPU_OT_StopStream, MPU_PT_Panel]

def register():
    bpy.types.WindowManager.mpu_com_port = bpy.props.EnumProperty(
        name="Port",
        description="Select available serial port",
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
        
    del bpy.types.WindowManager.mpu_com_port
    del bpy.types.WindowManager.map_roll_from
    del bpy.types.WindowManager.sign_roll
    del bpy.types.WindowManager.map_pitch_from
    del bpy.types.WindowManager.sign_pitch
    del bpy.types.WindowManager.map_yaw_from
    del bpy.types.WindowManager.sign_yaw

if __name__ == "__main__":
    register()