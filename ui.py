# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

from rigify.utils.errors import MetarigError
from . import generate


def is_metarig(obj):
    if not (obj and obj.data and obj.type == 'ARMATURE'):
        return False
    if 'rig_id' in obj.data:
        return False
    for b in obj.pose.bones:
        if b.rigify_type != "":
            return True
    return False

class Generate_WayRig(bpy.types.Operator):
    """Generates a rig from the active metarig armature"""
    bl_idname = "pose.wayrig_generate"
    bl_label = "WayRig Generate Rig"
    bl_options = {'UNDO'}
    bl_description = 'Generates a rig from the active metarig armature'

    @classmethod
    def poll(cls, context):
        return is_metarig(context.object)

    def execute(self, context):
        metarig = context.object
        try:
            generate.generate_rig(context, metarig)
        except MetarigError as rig_exception:
            import traceback
            traceback.print_exc()

            rigify_report_exception(self, rig_exception)
        except Exception as rig_exception:
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, 'Generation has thrown an exception: ' + str(rig_exception))
        else:
            self.report({'INFO'}, 'Successfully generated: "' + metarig.data.rigify_target_rig.name + '"')
        finally:
            bpy.ops.object.mode_set(mode='OBJECT')

        return {'FINISHED'}

def add_wayrig_to_menu(self, context):
    """Add Wayrig opertator to top menu """
    self.layout.operator(Generate_WayRig.bl_idname, text="Generate (WayRig)")


### Registering ###


classes = (
    Generate_WayRig,
)


def register():
    from bpy.utils import register_class

    # Classes.
    for cls in classes:
        register_class(cls)

    bpy.types.VIEW3D_MT_rigify.append(add_wayrig_to_menu)


def unregister():
    from bpy.utils import unregister_class

    # Classes.
    for cls in classes:
        unregister_class(cls)

    bpy.types.VIEW3D_MT_rigify.remove(add_wayrig_to_menu)
