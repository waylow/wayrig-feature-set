# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

from itertools import count

from rigify.utils.bones import align_chain_x_axis, put_bone
from rigify.utils.widgets_basic import create_circle_widget
from rigify.utils.layers import ControlLayersOption
from rigify.utils.naming import strip_org, make_derived_name
from rigify.utils.misc import map_list, pairwise_nozip, padnone
from rigify.utils.mechanism import driver_var_transform

from rigify.base_rig import stage

from ..chain_rigs import TweakChainRig

from ....utils.naming import ROOT_NAME


class Rig(TweakChainRig):
    def initialize(self):
        super().initialize()

        self.copy_rotation_axes = self.params.copy_rotation_axes

    # Prepare
    def prepare_bones(self):
        if self.params.roll_alignment == "automatic":
            align_chain_x_axis(self.obj, self.bones.org)

    # generate MCH Handles
    @stage.generate_bones
    def make_mch_chain(self):
        orgs = self.bones.org
        self.bones.mch = map_list(self.make_mch_handle, count(0), orgs + orgs[-1:])

    def make_mch_handle(self, i, org):
        if i < len(self.bones.org):
            
            name = self.copy_bone(org, make_derived_name(org, 'mch', '_tweak'), parent=False, scale=0.5)

        if i == len(self.bones.org):
            name = self.copy_bone(org, make_derived_name(org, 'mch', '_end_tweak'), parent=False, scale=0.5)
            put_bone(self.obj, name, self.get_bone(org).tail)

        return name

    
    # Parent
    @stage.parent_bones
    def parent_control_chain(self):
        # use_connect=False for backward compatibility
        self.parent_bone_chain(self.bones.ctrl.fk, use_connect=False)


    # Configure
    @stage.configure_bones
    def configure_tweak_chain(self):
        super().configure_tweak_chain()

        ControlLayersOption.TWEAK.assign(self.params, self.obj, self.bones.ctrl.tweak)

    def configure_tweak_bone(self, i, tweak):
        super().configure_tweak_bone(i, tweak)

        # Backward compatibility
        self.get_bone(tweak).rotation_mode = 'XYZ'


    def configure_fk_controls(self):
        orgs = self.bones.org
        for fk in orgs:
            self.get_bone(strip_org(fk)).rotation_mode = 'XYZ'


    def configure_tweak_chain(self):
        for args in zip(count(0), self.bones.ctrl.tweak):
            self.configure_tweak_bone(*args)

    def configure_tweak_bone(self, i, tweak):
        tweak_pb = self.get_bone(tweak)
        tweak_pb.rotation_mode = 'ZXY'

        if i == len(self.bones.org):
            tweak_pb.lock_rotation_w = False
            tweak_pb.lock_rotation = (False, False, False)
            tweak_pb.lock_scale = (False, True, False)
        else:
            tweak_pb.lock_rotation_w = False
            tweak_pb.lock_rotation = (False, False, False)
            tweak_pb.lock_scale = (False, True, False)

        if i > 0:
            self.make_rubber_tweak_property(i, tweak)

    def make_rubber_tweak_property(self, i, tweak):
        defval = 1.0
        text = 'Rubber Tweak'

        self.make_property(tweak, 'rubber_tweak', defval, max=2.0, soft_max=1.0)

        panel = self.script.panel_with_selected_check(self, [tweak])
        panel.custom_prop(tweak, 'rubber_tweak', text=text, slider=True)

    # Rig
    @stage.rig_bones
    def rig_control_chain(self):
        ctrls = self.bones.ctrl.fk
        for args in zip(count(0), ctrls, [None] + ctrls):
            self.rig_control_bone(*args)

    def rig_control_bone(self, i, ctrl, prev_ctrl):
        if prev_ctrl:
            self.make_constraint(
                ctrl, 'COPY_ROTATION', prev_ctrl,
                use_xyz=self.copy_rotation_axes,
                space='LOCAL', mix_mode='BEFORE',
            )
    
    @stage.rig_bones
    def rig_mch_handles(self):
        mchs = self.bones.mch
        tweaks = self.bones.ctrl.tweak 
        for args in zip(count(0), mchs, tweaks):
            self.rig_mch_handle(*args)

    def rig_mch_handle(self, i, mch, tweak):
        con = self.make_constraint(
            mch, 'COPY_TRANSFORMS', tweak,
        )

    @stage.parent_bones
    def parent_mch_handles(self):
        parent_bone = self.get_bone(self.bones.org[0]).parent
        if parent_bone is None:
            parent_name = ROOT_NAME
        else:
            parent_name = parent_bone.name
        
        for mch in self.bones.mch:
            self.set_bone_parent(mch, parent_name)
    
    ##############################
    # Deform chain

    @stage.rig_bones
    def rig_deform_chain(self):
        deform_bones = self.bones.deform
        tweaks = self.bones.ctrl.tweak
        next_tweaks = tweaks[1:]

        for args in zip(count(0), deform_bones, tweaks, next_tweaks):
            self.rig_deform_bone(*args)


    def rig_deform_bone(self, i, deform, tweak, next_tweak):

        self.make_constraint(deform, 'COPY_TRANSFORMS', self.bones.org[i])
        self.rig_deform_easing(i, deform, tweak, next_tweak)


    def rig_deform_easing(self, i, deform, tweak, next_tweak):
        pbone = self.get_bone(deform)

        if 'rubber_tweak' in self.get_bone(tweak):
            self.make_driver(pbone.bone, 'bbone_easein', variables=[(tweak, 'rubber_tweak')])
        else:
            pbone.bone.bbone_easein = 0.0

        if 'rubber_tweak' in self.get_bone(next_tweak):
            self.make_driver(pbone.bone, 'bbone_easeout', variables=[(next_tweak, 'rubber_tweak')])
        else:
            pbone.bone.bbone_easeout = 0.0


    @stage.configure_bones
    def configure_def_bones(self):
        deform_bones = self.bones.deform
        start_handles = self.bones.mch
        end_handles = start_handles[1:]
        for args in zip(count(0), deform_bones, start_handles, end_handles):
            self.configure_def_bone(*args)
        
        #add preserve volume slider to the first control only
        if self.params.make_preserve_volume:
            ctrl=self.bones.ctrl
            panel = self.script.panel_with_selected_check(self, [*ctrl.fk, *ctrl.tweak])
            text = 'Preserve Volume'
            self.make_property(ctrl.fk[0], 'volume_preserve', 1.0, description='Preserve volume in stretch')
            panel.custom_prop(ctrl.fk[0], 'volume_preserve', text=text, slider=True)


    def configure_def_bone(self, i, deform, start_handle, end_handle):
        # Start Handle
        self.obj.data.bones[deform].bbone_handle_type_start = 'TANGENT'
        self.obj.data.bones[deform].bbone_custom_handle_start = self.obj.data.bones[start_handle]
        self.obj.pose.bones[deform].bone.bbone_handle_use_scale_start = [True, False, True]

        # End Handle
        self.obj.data.bones[deform].bbone_handle_type_end = 'TANGENT'
        self.obj.data.bones[deform].bbone_custom_handle_end = self.obj.data.bones[end_handle]
        self.obj.pose.bones[deform].bone.bbone_handle_use_scale_end = [True, False, True]

       
    ##############################
    # ORG chain
    @stage.rig_bones
    def configure_org_bones(self):
        parent_bone = self.get_bone(self.bones.org[0]).parent.name
        for org in self.bones.org:
            self.make_constraint(org, 'COPY_SCALE', parent_bone, insert_index=1 )
            if self.params.make_preserve_volume:
                con = self.obj.pose.bones[org].constraints['Stretch To']
                self.make_driver(con, 'bulge', variables=[(self.obj.pose.bones[self.bones.ctrl.fk[0]], 'volume_preserve')])


    # Widgets
    def make_control_widget(self, i, ctrl):
        create_circle_widget(self.obj, ctrl, radius=0.3, head_tail=0.5)


    @classmethod
    def add_parameters(self, params):
        """ Add the parameters of this rig type to the
            RigifyParameters PropertyGroup
        """
        params.copy_rotation_axes = bpy.props.BoolVectorProperty(
            size=3,
            description="Automation axes",
            default=tuple([i == 0 for i in range(0, 3)])
            )

        params.make_preserve_volume = bpy.props.BoolProperty(
            name="Preserve Volume", default=True,
            description="Create slider for volume preservation"
        )

        # Setting up extra tweak layers
        ControlLayersOption.TWEAK.add_parameters(params)

        items = [('automatic', 'Automatic', ''), ('manual', 'Manual', '')]
        params.roll_alignment = bpy.props.EnumProperty(items=items, name="Bone roll alignment", default='automatic')


    @classmethod
    def parameters_ui(self, layout, params):
        """ Create the ui for the rig parameters.
        """
        r = layout.row()
        r.prop(params, "make_preserve_volume")

        r = layout.row()
        r.prop(params, "roll_alignment")

        row = layout.row(align=True)
        for i, axis in enumerate(['x', 'y', 'z']):
            row.prop(params, "copy_rotation_axes", index=i, toggle=True, text=axis)

        ControlLayersOption.TWEAK.parameters_ui(layout, params)


def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Bone_01')
    bone.head = 0.0000, 0.0000, 0.0000
    bone.tail = 0.0000, 0.0000, 0.3333
    bone.roll = 0.0000
    bone.use_connect = False
    bones['Bone_01'] = bone.name
    bone = arm.edit_bones.new('Bone_02')
    bone.head = 0.0000, 0.0000, 0.3333
    bone.tail = 0.0000, 0.0000, 0.6667
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Bone_01']]
    bones['Bone_02'] = bone.name
    bone = arm.edit_bones.new('Bone_03')
    bone.head = 0.0000, 0.0000, 0.6667
    bone.tail = 0.0000, 0.0000, 1.0000
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Bone_02']]
    bones['Bone_03'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Bone_01']]
    pbone.rigify_type = 'WayRig.limbs.tentacle'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    try:
        pbone.rigify_parameters.tweak_layers_extra = True
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.copy_rotation_axes = [False, False, False]
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['Bone_02']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Bone_03']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
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
        bone.bbone_x = bone.bbone_z = bone.length * 0.05
        arm.edit_bones.active = bone

    return bones
