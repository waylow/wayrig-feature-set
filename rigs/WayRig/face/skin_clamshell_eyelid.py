# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

from math import asin
from mathutils import Matrix

from rigify.base_rig import BaseRig

from rigify.utils.naming import strip_org, make_deformer_name, make_derived_name
from rigify.utils.widgets import layout_widget_dropdown, create_registered_widget
from ..widgets import create_triangle_widget

from rigify.utils.bones import put_bone, flip_bone
from ..basic.raw_copy import RelinkConstraintsMixin
from rigify.utils.mechanism import driver_var_transform



class Rig(BaseRig, RelinkConstraintsMixin):
    """ A clamshell eyelid that can connect to the basic_eye rig type.

    """
    def find_org_bones(self, pose_bone):
        return pose_bone.name


    def initialize(self):
        """ Gather and validate data about the rig.
        """
        self.org_name     = strip_org(self.bones.org)

    ####################################################
    # UTILITIES

    def get_eyelid_info(self):
        """ Collect some info about the height and length of eyelid bone
            to use when setting up the constraints (needs to be done in edit mode)
        """
        org = self.bones.org

        bone = self.get_bone(org)

        bone_height = bone.tail.z - bone.head.z
        bone_length = bone.length


        bone_flat_vector = (bone.tail - bone.head)
        bone_flat_vector.z = 0
        bone_flat_vector.normalize()
        bone_flat_vector *= ( bone_length * 0.25 )

        bone_run_vector = (bone.tail - bone.head)
        bone_run_vector.z = 0
        bone_run = bone_run_vector.length #using this to calculate the driver settings

        return bone_height, bone_length, bone_flat_vector, bone_run

        
    ####################################################
    # BONES
    #
    # ctrl:
    #   Control for moving the eyelid.
    #   
    # deform:
    #   Deforms the eyelid. 
    #
    ####################################################

    def generate_bones(self):
        bones = self.bones

        # Make a control bone
        bones.ctrl = self.copy_bone(bones.org, self.org_name, parent=True )
        bone = self.get_bone(bones.ctrl)
        flip_bone(self.obj, bones.ctrl)
        bone.length /= 2 
        bone.tail.z = bone.head.z
        bone.roll = 0
        # offset the bone
        matrix = Matrix.Translation(self.get_eyelid_info()[2])
        put_bone(self.obj, bone.name, self.get_eyelid_info()[2] + self.get_bone(bones.org).tail )

        # Make a deformation bone (copy of original, child of original).
        bones.deform = self.copy_bone(bones.org, make_deformer_name(self.org_name), bbone=True)


    def parent_bones(self):
        bones = self.bones

        self.set_bone_parent(bones.deform, bones.org, use_connect=False)

        new_parent = self.relink_bone_parent(bones.org)

        if new_parent:
            self.set_bone_parent(bones.ctrl, new_parent)
            self.set_bone_parent(bones.org, new_parent)


    def configure_bones(self):
        bones = self.bones

        self.copy_bone_properties(bones.org, bones.ctrl)

        ctrl = self.get_bone(bones.ctrl)
        ctrl.lock_rotation = (True, False, True)
        ctrl.lock_location = (True, True, False)
        ctrl.lock_scale = (True, True, True)


    def rig_bones(self):
        bones = self.bones

        bone = self.get_bone(bones.org)
        bone.rotation_mode = 'YXZ'

        self.relink_bone_constraints(bones.org)


        self.relink_move_constraints(bones.org, bones.ctrl, prefix='CTRL:')

        # Make Driver on the org bone - open/close
        # make_driver(owner, path, index=-1, type='SUM', expression=None, variables={}, polynomial=None, target_id=None)
        target_rotation = driver_var_transform(self.obj, bones.ctrl, type='LOC_Z', space='LOCAL')

        driver = self.make_driver(bone, 'rotation_euler', index=0, type='SUM', variables=[target_rotation], polynomial=[0, asin ( self.get_eyelid_info()[0]) / (self.get_eyelid_info()[1]) / (self.get_eyelid_info()[0])] )
        
        # driver. = 
        # con = self.make_constraint(bones.org, 'TRANSFORM', bones.ctrl)
        # con.name = con.name + '_location'
        # con.target = self.obj
        # con.subtarget = bones.ctrl
        # con.use_motion_extrapolate = True
        # con.target_space = 'LOCAL'
        # con.owner_space = 'LOCAL'

        # con.map_from = 'LOCATION'
        # con.from_min_z = self.get_eyelid_info()[0]
        # con.from_max_z = con.from_min_z * -1

        # con.map_to = 'ROTATION'
        # con.map_to_x_from = 'Z'
        # con.to_min_x_rot = ( asin ( self.get_eyelid_info()[0]) / (self.get_eyelid_info()[1])    ) 
        # con.to_max_x_rot = con.to_min_x_rot * -1


        # Constrain the org bone - twist
        con = self.make_constraint(bones.org, 'COPY_ROTATION', bones.ctrl)
        con.target = self.obj
        con.subtarget = bones.ctrl

        con.target_space = 'LOCAL_OWNER_ORIENT'
        con.owner_space = 'LOCAL'

        con.use_x = False
        con.use_z = False

        self.relink_move_constraints(bones.org, bones.deform, prefix='DEF:')

        # if the clamshell should be constrained to the eye-track
        if self.params.constrain_to_eyetrack:
            con = self.make_constraint(bones.ctrl, 'COPY_LOCATION')
            con.name = 'lid_follow'
            con.target = self.obj
            con.subtarget = self.params.track_bone
            con.use_x = False
            con.use_y = False
            con.use_offset = True
            con.target_space = 'LOCAL_OWNER_ORIENT'
            con.owner_space = 'LOCAL'


    def generate_widgets(self):
        bones = self.bones
        size = 0.5
        if self.params.flip_widget:
            size *= -1
        # Create control widget
        create_triangle_widget(self.obj, bones.ctrl, size=size)


    @classmethod
    def add_parameters(self, params):
        """ Add the parameters of this rig type to the
            RigifyParameters PropertyGroup
        """
        params.constrain_to_eyetrack= bpy.props.BoolProperty(
            name="Constrain to Eye Track",
            default=False,
            description="Constrain to (basic_eye rig) eye track control (eye lid follow must be enabled on that rig)"
        )

        params.track_bone= bpy.props.StringProperty(
            name="Eye Track Bone Name",
            default='',
            description="The name of the bone the damped track to target (in the basic_eye rig)"
        )

        params.flip_widget= bpy.props.BoolProperty(
            name="Flip widget",
            default=False,
            description="Flip the triangle widget",
        )
        self.add_relink_constraints_params(params)


    @classmethod
    def parameters_ui(self, layout, params):
        """ Create the ui for the rig parameters.
        """
        col = layout.column()
        col.prop(params, "constrain_to_eyetrack", text="Constrain to eye track")
        if params.constrain_to_eyetrack:
            col.prop(params, "track_bone", text="Eye track bone")

        col.prop(params, "flip_widget", text="Flip Widget")

        self.add_relink_constraints_ui(layout, params)

        if params.relink_constraints:
            col = layout.column()
            col.label(text="'CTRL:...' constraints are moved to the control bone.", icon='INFO')
            col.label(text="'DEF:...' constraints are moved to the deform bone.", icon='INFO')


def create_sample(obj):
    """ Create a sample metarig for this rig type.
    """
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('EyeLid_Top')
    bone.head[:] = 0.0000, 0.0000, 0.0000
    bone.tail[:] = 0.0000, 0.0000, 0.2000
    bone.roll = 0.0000
    bone.use_connect = False
    bones['EyeLid_Top'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Bone']]
    pbone.rigify_type = 'WayRig.face.skin_clamshell_eyelid'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'

    bpy.ops.object.mode_set(mode='EDIT')
    for bone in arm.edit_bones:
        bone.select = False
        bone.select_head = False
        bone.select_tail = False
    for b in bones:
        bone = arm.edit_bones[bones[b]]
        bone.select = True
        bone.select_head = True
        bone.select_tail = True
        arm.edit_bones.active = bone

    return bones
