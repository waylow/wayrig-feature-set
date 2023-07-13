# SPDX-License-Identifier: GPL-2.0-or-later

import bpy
import math

from mathutils import Vector, Matrix
from math import radians

from rigify.utils.rig import is_rig_base_bone
from rigify.utils.bones import align_chain_x_axis, align_bone_x_axis, align_bone_z_axis
from rigify.utils.bones import put_bone, align_bone_orientation, align_bone_to_axis, flip_bone, set_bone_widget_transform
from rigify.utils.naming import make_derived_name
from rigify.utils.misc import matrix_from_axis_roll, matrix_from_axis_pair
from rigify.utils.widgets import adjust_widget_transform_mesh

from rigify.rigs.widgets import create_foot_widget, create_ball_socket_widget
from rigify.utils.widgets_basic import create_sphere_widget
from ..widgets import create_triangle_widget
from rigify.base_rig import stage

from .limb_rigs import BaseLimbRig


DEG_360 = math.pi * 2
ALL_TRUE = (True, True, True)


class Rig(BaseLimbRig):
    """Human leg rig."""

    min_valid_orgs = max_valid_orgs = 4

    def find_org_bones(self, bone):
        bones = super().find_org_bones(bone)

        for b in self.get_bone(bones.main[2]).bone.children:
            if not b.use_connect and not b.children and not is_rig_base_bone(self.obj, b.name):
                bones.heel = b.name
                break
        else:
            self.raise_error("Heel bone not found.")

        return bones

    def initialize(self):
        super().initialize()

        self.pivot_type = self.params.foot_pivot_type
        self.heel_euler_order = 'ZXY' if self.main_axis == 'x' else 'XZY'
        self.use_ik_toe = self.params.extra_ik_toe

        if self.use_ik_toe:
            self.fk_name_suffix_cutoff = 3
            self.fk_ik_layer_cutoff = 4

        assert self.pivot_type in {'ANKLE', 'TOE', 'ANKLE_TOE'}

    def prepare_bones(self):
        orgs = self.bones.org.main
        foot = self.get_bone(orgs[2])

        ik_y_axis = (0, 1, 0)
        foot_y_axis = -self.vector_without_z(foot.y_axis)
        foot_x = foot_y_axis.cross((0, 0, 1))

        if self.params.rotation_axis == 'automatic':
            align_chain_x_axis(self.obj, orgs[0:2])

            # Orient foot and toe
            align_bone_x_axis(self.obj, orgs[2], foot_x)
            align_bone_x_axis(self.obj, orgs[3], -foot_x)

            align_bone_x_axis(self.obj, self.bones.org.heel, Vector((0, 0, 1)))

        elif self.params.auto_align_extremity:
            if self.main_axis == 'x':
                align_bone_x_axis(self.obj, orgs[2], foot_x)
                align_bone_x_axis(self.obj, orgs[3], -foot_x)
            else:
                align_bone_z_axis(self.obj, orgs[2], foot_x)
                align_bone_z_axis(self.obj, orgs[3], -foot_x)

        else:
            ik_y_axis = foot_y_axis

        # Orientation of the IK main and roll control bones
        self.ik_matrix = matrix_from_axis_roll(ik_y_axis, 0)
        self.roll_matrix = matrix_from_axis_pair(ik_y_axis, foot_x, self.main_axis)

    ####################################################
    # EXTRA BONES
    #
    # org:
    #   heel:
    #     Heel location marker bone
    # ctrl:
    #   ik_spin:
    #     Toe spin control.
    #   heel:
    #     Foot roll control
    #   ik_toe:
    #     If enabled, toe control for IK chain.
    # mch:
    #   heel[]:
    #     Chain of bones implementing foot roll.
    #   ik_toe_parent:
    #      If using split IK toe, parent of the IK toe control.
    #  BENDABLE FOOT:
    #   If using bendable foot, extra bones to make foot flexible.
    #   TOE BREAK:
    #   If using this option, extra 2 bones to add that functionality
    ####################################################

    ####################################################
    # IK controls

    def get_tail_ik_controls(self):
        return [self.bones.ctrl.ik_toe] if self.use_ik_toe else []

    def get_extra_ik_controls(self):
        controls = super().get_extra_ik_controls() + [self.bones.ctrl.heel]
        if self.pivot_type == 'ANKLE_TOE':
            controls += [self.bones.ctrl.ik_spin]
        return controls

    def make_ik_control_bone(self, orgs):
        name = self.copy_bone(orgs[2], make_derived_name(orgs[2], 'ctrl', '_IK'))
        if self.pivot_type == 'TOE':
            put_bone(self.obj, name, self.get_bone(name).tail, matrix=self.ik_matrix)

        else:
            put_bone(self.obj, name, None, matrix=self.ik_matrix)
        return name

    def build_ik_pivot(self, ik_name, **args):
        heel_bone = self.get_bone(self.bones.org.heel)
        args = {
            'position': (heel_bone.head + heel_bone.tail)/2,
            **args
        }
        return super().build_ik_pivot(ik_name, **args)

    def register_switch_parents(self, pbuilder):
        super().register_switch_parents(pbuilder)

        pbuilder.register_parent(self, self.bones.org.main[2], exclude_self=True, tags={'limb_end'})

    def make_ik_ctrl_widget(self, ctrl):
        obj = create_foot_widget(self.obj, ctrl)

        if self.pivot_type != 'TOE':
            ctrl = self.get_bone(ctrl)
            org = self.get_bone(self.bones.org.main[2])
            offset = org.tail - (ctrl.custom_shape_transform or ctrl).head
            adjust_widget_transform_mesh(obj, Matrix.Translation(offset))

    ####################################################
    # IK pivot controls

    def get_ik_pivot_output(self):
        if self.pivot_type == 'ANKLE_TOE':
            return self.bones.ctrl.ik_spin
        else:
            return self.get_ik_control_output()

    @stage.generate_bones
    def make_ik_pivot_controls(self):
        if self.pivot_type == 'ANKLE_TOE':
            self.bones.ctrl.ik_spin = self.make_ik_spin_bone(self.bones.org.main)

    def make_ik_spin_bone(self, orgs):
        name = self.copy_bone(orgs[2], make_derived_name(orgs[2], 'ctrl', '_spin_IK'))
        put_bone(self.obj, name, self.get_bone(orgs[3]).head, matrix=self.ik_matrix, scale=0.5)
        return name

    @stage.parent_bones
    def parent_ik_pivot_controls(self):
        if self.pivot_type == 'ANKLE_TOE':
            self.set_bone_parent(self.bones.ctrl.ik_spin, self.get_ik_control_output())


    @stage.configure_bones
    def configure_ik_spin_bone(self):
        spin = self.get_bone(self.bones.ctrl.ik_spin)
        spin.rotation_mode = 'XYZ'
        spin.lock_scale = True, True, True
        spin.lock_location = True, True, True

    @stage.apply_bones
    def apply_ik_spin_bone(self):
        if self.params.move_foot_spin:
            orgs = self.bones.org.main
            name = make_derived_name(orgs[2], 'ctrl', '_spin_IK')
            tail = self.get_bone(orgs[3]).tail
            tail_floored = [tail.x, tail.y, 0 ]
            put_bone(self.obj, name, tail_floored, matrix=self.ik_matrix, scale=0.5)



    @stage.generate_widgets
    def make_ik_spin_control_widget(self):
        if self.pivot_type == 'ANKLE_TOE':
            obj = create_ball_socket_widget(self.obj, self.bones.ctrl.ik_spin, size=0.75)
            rotfix = Matrix.Rotation(math.pi/2, 4, self.main_axis.upper())
            adjust_widget_transform_mesh(obj, rotfix, local=True)

    ####################################################
    # Heel control

    @stage.generate_bones
    def make_heel_control_bone(self):
        org = self.bones.org.main[2]
        name = self.copy_bone(org, make_derived_name(org, 'ctrl', '_Heel'))
        put_bone(self.obj, name, None, matrix=self.roll_matrix, scale=0.5)
        self.bones.ctrl.heel = name

    @stage.parent_bones
    def parent_heel_control_bone(self):
        self.set_bone_parent(self.bones.ctrl.heel, self.get_ik_pivot_output(), inherit_scale='AVERAGE')

    @stage.configure_bones
    def configure_heel_control_bone(self):
        bone = self.get_bone(self.bones.ctrl.heel)
        bone.lock_location = True, True, True
        bone.rotation_mode = self.heel_euler_order
        bone.lock_scale = True, True, True

    @stage.generate_widgets
    def generate_heel_control_widget(self):
        create_ball_socket_widget(self.obj, self.bones.ctrl.heel)

    ####################################################
    # IK toe control

    @stage.generate_bones
    def make_ik_toe_control(self):
        if self.use_ik_toe:
            toe = self.bones.org.main[3]
            self.bones.ctrl.ik_toe = self.make_ik_toe_control_bone(toe)
            self.bones.mch.ik_toe_parent = self.make_ik_toe_parent_mch_bone(toe)

    def make_ik_toe_control_bone(self, org):
        return self.copy_bone(org, make_derived_name(org, 'ctrl', '_IK'))

    def make_ik_toe_parent_mch_bone(self, org):
        return self.copy_bone(org, make_derived_name(org, 'mch', '_IK_parent'), scale=1/3)

    @stage.parent_bones
    def parent_ik_toe_control(self):
        if self.use_ik_toe:
            mch = self.bones.mch
            align_bone_orientation(self.obj, mch.ik_toe_parent, self.get_mch_heel_toe_output())

            self.set_bone_parent(mch.ik_toe_parent, mch.ik_target, use_connect=True)
            self.set_bone_parent(self.bones.ctrl.ik_toe, mch.ik_toe_parent)

    @stage.configure_bones
    def configure_ik_toe_control(self):
        if self.use_ik_toe:
            self.copy_bone_properties(self.bones.org.main[3], self.bones.ctrl.ik_toe, props=False)

    @stage.rig_bones
    def rig_ik_toe_control(self):
        if self.use_ik_toe:
            self.make_constraint(self.bones.mch.ik_toe_parent, 'COPY_TRANSFORMS', self.get_mch_heel_toe_output())

    @stage.generate_widgets
    def make_ik_toe_control_widget(self):
        if self.use_ik_toe:
            self.make_fk_control_widget(3, self.bones.ctrl.ik_toe)

    ####################################################
    # Heel roll MCH

    def get_mch_heel_toe_output(self):
        return self.bones.mch.heel[-3]

    @stage.generate_bones
    def make_roll_mch_chain(self):
        orgs = self.bones.org.main
        self.bones.mch.heel = self.make_roll_mch_bones(orgs[2], orgs[3], self.bones.org.heel)

    def make_roll_mch_bones(self, foot, toe, heel):
        foot_bone = self.get_bone(foot)
        heel_bone = self.get_bone(heel)

        heel_middle = (heel_bone.head + heel_bone.tail) / 2

        result = self.copy_bone(foot, make_derived_name(foot, 'mch', '_roll'), scale=0.25)

        roll1 = self.copy_bone(toe, make_derived_name(heel, 'mch', '_roll1'), scale=0.3)
        roll2 = self.copy_bone(toe, make_derived_name(heel, 'mch', '_roll2'), scale=0.3)
        rock1 = self.copy_bone(heel, make_derived_name(heel, 'mch', '_rock1'))
        rock2 = self.copy_bone(heel, make_derived_name(heel, 'mch', '_rock2'))

        put_bone(self.obj, roll1, None, matrix=self.roll_matrix)
        put_bone(self.obj, roll2, heel_middle, matrix=self.roll_matrix)
        put_bone(self.obj, rock1, heel_bone.tail, matrix=self.roll_matrix, scale=0.5)
        put_bone(self.obj, rock2, heel_bone.head, matrix=self.roll_matrix, scale=0.5)

        return [ rock2, rock1, roll2, roll1, result ]

    @stage.parent_bones
    def parent_roll_mch_chain(self):
        chain = self.bones.mch.heel
        self.set_bone_parent(chain[0], self.get_ik_pivot_output())
        self.parent_bone_chain(chain)

    @stage.rig_bones
    def rig_roll_mch_chain(self):
        self.rig_roll_mch_bones(self.bones.mch.heel, self.bones.ctrl.heel, self.bones.org.heel)

    def rig_roll_mch_bones(self, chain, heel, org_heel):
        rock2, rock1, roll2, roll1, result = chain

        # This order is required for correct working of the constraints
        for bone in chain:
            self.get_bone(bone).rotation_mode = self.heel_euler_order

        self.make_constraint(roll1, 'COPY_ROTATION', heel, space='POSE')

        if self.main_axis == 'x':
            self.make_constraint(roll2, 'COPY_ROTATION', heel, space='LOCAL', use_xyz=(True, False, False))
            self.make_constraint(roll2, 'LIMIT_ROTATION', min_x=-DEG_360, space='LOCAL')
        else:
            self.make_constraint(roll2, 'COPY_ROTATION', heel, space='LOCAL', use_xyz=(False, False, True))
            self.make_constraint(roll2, 'LIMIT_ROTATION', min_z=-DEG_360, space='LOCAL')

        direction = self.get_main_axis(self.get_bone(heel)).dot(self.get_bone(org_heel).vector)

        if direction < 0:
            rock2, rock1 = rock1, rock2

        self.make_constraint(
            rock1, 'COPY_ROTATION', heel, space='LOCAL',
            use_xyz=(False, True, False),
        )
        self.make_constraint(
            rock2, 'COPY_ROTATION', heel, space='LOCAL',
            use_xyz=(False, True, False),
        )

        self.make_constraint(rock1, 'LIMIT_ROTATION', max_y=DEG_360, space='LOCAL')
        self.make_constraint(rock2, 'LIMIT_ROTATION', min_y=-DEG_360, space='LOCAL')


    ####################################################
    # FK parents MCH chain

    def parent_fk_parent_bone(self, i, parent_mch, prev_ctrl, org, prev_org):
        if i == 3:
            if not self.use_ik_toe:
                align_bone_orientation(self.obj, parent_mch, self.get_mch_heel_toe_output())

                self.set_bone_parent(parent_mch, prev_org, use_connect=True)
            else:
                self.set_bone_parent(parent_mch, prev_ctrl, use_connect=True, inherit_scale='ALIGNED')

        else:
            super().parent_fk_parent_bone(i, parent_mch, prev_ctrl, org, prev_org)

    def rig_fk_parent_bone(self, i, parent_mch, org):
        if i == 3:
            if not self.use_ik_toe:
                con = self.make_constraint(parent_mch, 'COPY_TRANSFORMS', self.get_mch_heel_toe_output())

                self.make_driver(con, 'influence', variables=[(self.prop_bone, 'IK_FK')], polynomial=[1.0, -1.0])

        else:
            super().rig_fk_parent_bone(i, parent_mch, org)

    ####################################################
    # IK system MCH

    def get_ik_input_bone(self):
        return self.bones.mch.heel[-1]

    @stage.parent_bones
    def parent_ik_mch_chain(self):
        super().parent_ik_mch_chain()

        self.set_bone_parent(self.bones.mch.ik_target, self.bones.mch.heel[-1])


    ####################################################
    # BENDABLE FOOT

    @stage.generate_bones
    def make_foot_bend_bones(self):
        if self.params.make_bendable_foot:
            orgs = self.bones.org.main

            #toe_01_tweak
            toe_01 = orgs[2]
            toe_01_tweak = self.copy_bone(toe_01, make_derived_name(orgs[3], 'ctrl', '_01_tweak'), scale = 0.25)
            flip_bone(self.obj, toe_01_tweak)
            self.obj.data.edit_bones[toe_01_tweak].tail.z = self.obj.data.edit_bones[toe_01_tweak].head.z
            put_bone(self.obj, toe_01_tweak, pos=self.obj.pose.bones[orgs[3]].head, matrix=None)

            #toe_02_tweak
            toe_02 = orgs[3]
            toe_02_tweak = self.copy_bone(toe_02, make_derived_name(orgs[3], 'ctrl', '_02_tweak'), scale = 0.25)
            flip_bone(self.obj, toe_02_tweak)
            self.obj.data.edit_bones[toe_02_tweak].tail.z = self.obj.data.edit_bones[toe_02_tweak].head.z
            put_bone(self.obj, toe_02_tweak, pos=self.obj.pose.bones[orgs[3]].tail, matrix=None)

            #Foot handle_end
            foot = orgs[2]
            foot_handle_end = self.copy_bone(foot, make_derived_name(orgs[2], 'mch', '_handle_end'), scale = 0.15)
            put_bone(self.obj, foot_handle_end, pos=self.obj.pose.bones[orgs[2]].tail, matrix=None)

            #Toe handle_start
            toe_handle_start = self.copy_bone(toe_02, make_derived_name(orgs[3], 'mch', '_handle_start'), scale = 0.15)

            #Toe handle_end
            toe_handle_end = self.copy_bone(toe_02, make_derived_name(orgs[3], 'mch', '_handle_end'), scale = 0.15)
            put_bone(self.obj, toe_handle_end, pos=self.obj.pose.bones[orgs[3]].tail, matrix=None)

    @stage.parent_bones
    def parent_foot_bend_bones(self):
        if self.params.make_bendable_foot:
            orgs = self.bones.org.main
            # TWEAK 01
            self.set_bone_parent(make_derived_name(orgs[3], 'ctrl', '_01_tweak'), orgs[2], use_connect=False, inherit_scale=None)
            # TWEAK 02
            self.set_bone_parent(make_derived_name(orgs[3], 'ctrl', '_02_tweak'), orgs[3], use_connect=False, inherit_scale=None)
            #HANDLE FOOT END
            self.set_bone_parent(make_derived_name(orgs[2], 'mch', '_handle_end'), make_derived_name(orgs[3], 'ctrl', '_01_tweak'), use_connect=False, inherit_scale=None)
            #HANDLE TOE START
            self.set_bone_parent(make_derived_name(orgs[3], 'mch', '_handle_start'), make_derived_name(orgs[3], 'ctrl', '_01_tweak'), use_connect=False, inherit_scale=None)
            #HANDLE TOE END
            self.set_bone_parent(make_derived_name(orgs[3], 'mch', '_handle_end'), make_derived_name(orgs[3], 'ctrl', '_02_tweak'), use_connect=False, inherit_scale=None)


    @stage.configure_bones
    def configure_foot_bend_bones(self):
        if self.params.make_bendable_foot:
            orgs = self.bones.org.main

            #Foot DEF
            foot = self.bones.deform[-2]
            self.obj.data.bones[foot].bbone_handle_type_start = 'TANGENT'
            self.obj.data.bones[foot].bbone_handle_type_end = 'TANGENT'
            self.obj.data.bones[foot].bbone_custom_handle_start = self.obj.data.bones[orgs[2]]
            self.obj.data.bones[foot].bbone_custom_handle_end = self.obj.data.bones[make_derived_name(orgs[2], 'mch', '_handle_end')]
            self.obj.data.bones[foot].bbone_handle_use_scale_end[0] = True
            self.obj.data.bones[foot].bbone_handle_use_scale_end[2] = True
            self.obj.data.bones[foot].inherit_scale = 'ALIGNED'

            #Toe DEF
            toe = self.bones.deform[-1]
            self.obj.data.bones[toe].bbone_handle_type_start = 'TANGENT'
            self.obj.data.bones[toe].bbone_handle_type_end = 'TANGENT'
            self.obj.data.bones[toe].bbone_custom_handle_start = self.obj.data.bones[make_derived_name(orgs[3], 'mch', '_handle_start')]
            self.obj.data.bones[toe].bbone_custom_handle_end = self.obj.data.bones[make_derived_name(orgs[3], 'mch', '_handle_end')]
            self.obj.data.bones[toe].bbone_handle_use_scale_start[0] = True
            self.obj.data.bones[toe].bbone_handle_use_scale_start[2] = True
            self.obj.data.bones[toe].bbone_handle_use_scale_end[0] = True
            self.obj.data.bones[toe].bbone_handle_use_scale_end[2] = True

            # put toe tweak bones on the correct layers
            tweak_bones = [make_derived_name(orgs[3], 'ctrl', '_01_tweak'),make_derived_name(orgs[3], 'ctrl', '_02_tweak')]
            for bone in tweak_bones:
                for i, (bl,tl) in enumerate(zip(self.obj.pose.bones[bone].bone.layers, self.params.tweak_layers)):
                    self.obj.pose.bones[bone].bone.layers[i] = tl

                # Euler the toe tweak controls
                self.obj.pose.bones[bone].rotation_mode = 'ZXY'

                # locks on the toe tweak controls
                self.obj.pose.bones[bone].lock_rotation = [True, False, True]
                self.obj.pose.bones[bone].lock_scale[1] = True


    @stage.rig_bones
    def rig_foot_bend_bones(self):
        if self.params.make_bendable_foot:
            orgs = self.bones.org.main
            #Foot DEF
            foot = self.bones.deform[-2]
            con = self.obj.pose.bones[foot].constraints['Stretch To']
            con.subtarget = make_derived_name(orgs[3], 'ctrl', '_01_tweak')

            #Toe DEF
            toe = self.bones.deform[-1]

            con = self.obj.pose.bones[toe].constraints.new(type='COPY_LOCATION')
            con.target = self.obj
            con.subtarget = make_derived_name(orgs[3], 'ctrl', '_01_tweak')
            
            con = self.obj.pose.bones[toe].constraints.new(type='COPY_ROTATION')
            con.target = self.obj
            con.subtarget = make_derived_name(orgs[3], 'ctrl', '_01_tweak')
            con.mix_mode = 'BEFORE'
            con.owner_space = 'LOCAL'
            con.target_space = 'LOCAL'

            con = self.obj.pose.bones[toe].constraints.new(type='COPY_SCALE')
            con.target = self.obj
            con.subtarget = make_derived_name(orgs[3], 'ctrl', '_01_tweak')

            con = self.obj.pose.bones[toe].constraints.new(type='STRETCH_TO')
            con.target = self.obj
            con.subtarget = make_derived_name(orgs[3], 'ctrl', '_02_tweak')
            con.keep_axis = 'PLANE_X'


            # con = self.obj.pose.bones[toe].constraints['Copy Transforms']
            # con.subtarget = make_derived_name(orgs[3], 'ctrl', '_01_tweak')
            # con.mute = True


    @stage.generate_widgets
    def make_foot_bend_widgets(self):
        if self.params.make_bendable_foot:
            orgs = self.bones.org.main
            create_sphere_widget(self.obj, make_derived_name(orgs[3], 'ctrl', '_01_tweak'))
            create_sphere_widget(self.obj, make_derived_name(orgs[3], 'ctrl', '_02_tweak'))


    ####################################################
    # TOE BREAK

    @stage.generate_bones
    def make_toe_break_bones(self):
        if self.params.make_toe_break:
            orgs = self.bones.org.main

            #MCH - Toe Reverse
            toe = orgs[3]
            mch_toe_reverse = self.copy_bone(toe, make_derived_name(toe, 'mch', '_IK_reverse'))
            flip_bone(self.obj, mch_toe_reverse)

            #MCH = Foot Reverse
            foot = orgs[2]
            mch_foot_reverse = self.copy_bone(foot, make_derived_name(foot, 'mch', '_IK_reverse'))
            flip_bone(self.obj, mch_foot_reverse)

            #Toe-reverse
            toe_reverse = self.copy_bone(toe, make_derived_name(toe, 'ctrl', '_IK_reverse'), scale = 0.25)
            tail = self.get_bone(orgs[3]).tail
            tail_floored = [tail.x, tail.y, 0 ]
            put_bone(self.obj, toe_reverse, tail_floored, matrix=self.ik_matrix, scale=0.5)

            #Foot-reverse
            foot_reverse = self.copy_bone(mch_foot_reverse, make_derived_name(foot, 'ctrl',  '_IK_reverse'), scale = 0.25)
            align_bone_orientation(self.obj, foot_reverse, self.bones.ctrl.heel)


    @stage.parent_bones
    def parent_toe_break_bones(self):
        if self.params.make_toe_break:
            orgs = self.bones.org.main
            heel = self.bones.org.heel
            roll2 = make_derived_name(heel, 'mch', '_roll2')

            #MCH Toe Reverse
            self.set_bone_parent(make_derived_name(orgs[3], 'mch', '_IK_reverse'),  make_derived_name(orgs[3], 'ctrl', '_IK_reverse'), use_connect=False, inherit_scale=None)
            #Toe Reverse
            self.set_bone_parent(make_derived_name(orgs[3], 'ctrl', '_IK_reverse'), roll2, use_connect=False, inherit_scale=None)
           #MCH Foot Reverse
            self.set_bone_parent(make_derived_name(orgs[2], 'mch', '_IK_reverse'), make_derived_name(orgs[2], 'ctrl', '_IK_reverse'), use_connect=False, inherit_scale=None)
           #Foot Reverse
            self.set_bone_parent(make_derived_name(orgs[2], 'ctrl', '_IK_reverse'), roll2, use_connect=False, inherit_scale=None)
            

    @stage.configure_bones
    def configure_toe_break_bones(self):
        if self.params.make_toe_break:
            orgs = self.bones.org.main

            reverse_bones = [make_derived_name(orgs[3], 'ctrl', '_IK_reverse'),make_derived_name(orgs[2], 'ctrl', '_IK_reverse')]
            for bone in reverse_bones:
                # Euler bones
                self.obj.pose.bones[bone].rotation_mode = 'ZXY'

                # locks 
                self.obj.pose.bones[bone].lock_location = [True, True, True]
                self.obj.pose.bones[bone].lock_scale = [True, True, True]

            # Add Toe Break Property
            panel = self.script.panel_with_selected_check(self, [self.bones.ctrl.heel, ])
            text = 'Toe Break ('+ self.bones.ctrl.heel + ')'
            self.make_property(self.bones.ctrl.heel, 'toe_break', 60, min= 0, max = 180, description='Angle to start rolling onto the toe')
            panel.custom_prop(self.bones.ctrl.heel, 'toe_break', text=text, slider=True)


    @stage.rig_bones
    def rig_toe_break_bones(self):
        if self.params.make_toe_break:
            orgs = self.bones.org.main
            
            #MCH - Toe Reverse
            toe_reverse = make_derived_name(orgs[3], 'ctrl', '_IK_reverse')
            con = self.obj.pose.bones[toe_reverse].constraints.new(type='TRANSFORM')
            con.target = self.obj
            con.subtarget = self.bones.ctrl.heel
            con.target_space = 'LOCAL'
            con.owner_space = 'LOCAL'
            con.map_from = 'ROTATION'
            con.map_to = 'ROTATION'
            con.mix_mode_rot = 'ADD'

            self.make_driver(con, 'from_min_x_rot', type='SUM', expression='radians(var)', variables=[(self.bones.ctrl.heel, 'toe_break')], polynomial=None)
            con.from_max_x_rot = radians(180)
            con.to_max_x_rot = radians(180)

            #Foot Reverse
            foot_reverse = make_derived_name(orgs[2], 'ctrl', '_IK_reverse')
            mch_foot_reverse = make_derived_name(orgs[2], 'mch', '_IK_reverse')
            toe_reverse = make_derived_name(orgs[3], 'ctrl', '_IK_reverse')
            mch_toe_reverse = make_derived_name(orgs[3], 'mch', '_IK_reverse')

            con = self.obj.pose.bones[foot_reverse].constraints.new(type='COPY_LOCATION')
            con.target = self.obj
            con.subtarget = mch_toe_reverse
            con.head_tail = 1.0

            # Foot Roll
            con = self.obj.pose.bones[foot_reverse].constraints.new(type='TRANSFORM')
            con.name = 'Foot Roll'
            con.target = self.obj
            con.subtarget = self.bones.ctrl.heel
            con.target_space = 'LOCAL'
            con.owner_space = 'LOCAL'
            con.map_from = 'ROTATION'
            con.map_to = 'ROTATION'
            con.mix_mode_rot = 'ADD'

            con.from_max_x_rot = radians(150)
            con.to_max_x_rot = radians(180)

            con.from_min_z_rot = radians(-180)
            con.to_min_z_rot = radians(-180)

            con.from_max_z_rot = radians(180)
            con.to_max_z_rot = radians(180)

            # Counter Roll
            con = self.obj.pose.bones[foot_reverse].constraints.new(type='TRANSFORM')
            con.name = 'Foot Roll Counter'
            con.target = self.obj
            con.subtarget = self.bones.ctrl.heel
            con.target_space = 'LOCAL'
            con.owner_space = 'LOCAL'
            con.map_from = 'ROTATION'
            con.map_to = 'ROTATION'
            #con.mix_mode_rot = 'BEFORE'

            self.make_driver(con, 'from_min_x_rot', type='SUM', expression='radians(var)', variables=[(self.bones.ctrl.heel, 'toe_break')], polynomial=None)
            con.from_max_x_rot = radians(180)
            
            self.make_driver(con, 'to_max_x_rot', type='SUM', expression='-radians(var)', variables=[(self.bones.ctrl.heel, 'toe_break')], polynomial=None)

            #Edit MCH-Heel_roll1
            roll1 = self.get_bone(make_derived_name(self.bones.org.heel, 'mch', '_roll1'))
            con = self.obj.pose.bones[roll1.name].constraints['Copy Rotation']
            con.use_x = False

            con = self.obj.pose.bones[roll1.name].constraints.new(type='COPY_ROTATION')
            con.target = self.obj
            con.subtarget = foot_reverse
            con.use_y = False
            con.use_z = False
            con.target_space = 'LOCAL'
            con.owner_space = 'LOCAL'

            #Edit MCH-Thigh_IK_target
            thigh_IK_target = self.get_bone(make_derived_name(orgs[0], 'mch', '_IK_target'))
            con = self.obj.pose.bones[thigh_IK_target.name].constraints['Copy Location']
            con.target = self.obj
            con.subtarget =  mch_foot_reverse
            con.head_tail = 1.0
            #Add Damped track on the MCH-Thigh_IK_Target
            con = self.obj.pose.bones[thigh_IK_target.name].constraints.new(type='DAMPED_TRACK')
            con.target = self.obj
            con.subtarget = foot_reverse
            con.track_axis = 'TRACK_Y'
            
            #Edit the MCH-Toe
            if self.params.extra_ik_toe:
                mch_toe = make_derived_name(orgs[3], 'mch', '_IK_parent')
            else:
                mch_toe = make_derived_name(orgs[3], 'mch')
            con = self.obj.pose.bones[mch_toe].constraints.new(type='COPY_ROTATION')
            con.target = self.obj
            con.subtarget = toe_reverse
            con.target_space = 'WORLD'
            con.owner_space = 'WORLD'

            self.make_driver(con, 'influence', variables=[(self.obj.pose.bones[self.bones.ctrl.master], 'IK_FK')], polynomial=[1.0,-1.0])


    @stage.generate_widgets
    def make_toe_break_widgets(self):
        if self.params.make_toe_break:
            orgs = self.bones.org.main
            foot_reverse = make_derived_name(orgs[2], 'ctrl', '_IK_reverse')
            mch_foot_reverse = make_derived_name(orgs[2], 'mch', '_IK_reverse')
            toe_reverse = make_derived_name(orgs[3], 'ctrl', '_IK_reverse')
            mch_toe_reverse = make_derived_name(orgs[3], 'mch', '_IK_reverse')
            
            # Foot Reverse
            foot_widget = create_triangle_widget(self.obj, foot_reverse)
            rotfix = Matrix.Rotation(-math.pi/2, 4, 'X')
            adjust_widget_transform_mesh(foot_widget, rotfix, local=True)
            set_bone_widget_transform(self.obj, foot_reverse, mch_foot_reverse)  # NOT WORKING!
            
            
            # Toe Reverse
            toe_widget = create_triangle_widget(self.obj, toe_reverse, size=2.0)    
            set_bone_widget_transform(self.obj, toe_reverse, mch_toe_reverse)
            adjust_widget_transform_mesh(toe_widget, rotfix, local=True)  # NOT WORKING!

    ####################################################
    # Settings

    @classmethod
    def add_parameters(self, params):
        super().add_parameters(params)

        items = [
            ('ANKLE', 'Ankle',
             'The foots pivots at the ankle'),
            ('TOE', 'Toe',
             'The foot pivots around the base of the toe'),
            ('ANKLE_TOE', 'Ankle and Toe',
             'The foots pivots at the ankle, with extra toe pivot'),
        ]

        params.foot_pivot_type = bpy.props.EnumProperty(
            items   = items,
            name    = "Foot Pivot",
            default = 'ANKLE_TOE'
        )

        params.extra_ik_toe = bpy.props.BoolProperty(
            name='Separate IK Toe',
            default=False,
            description="Generate a separate IK toe control for better IK/FK snapping"
        )

        params.move_foot_spin = bpy.props.BoolProperty(
            name='Move toe pivot to toe end',
            default=False,
            description="Generate the foot spin control at the tail of the toe (on the floor)"
        )

        params.make_bendable_foot = bpy.props.BoolProperty(
            name='Make Bendable Foot',
            default=True,
            description="Add tweaks to the foot, useful for cartoony characters"
        )

        params.make_toe_break = bpy.props.BoolProperty(
            name='Add Toe Break',
            default=True,
            description="Make the Foot automatically roll onto the toe"
        )


    @classmethod
    def parameters_ui(self, layout, params):
        layout.prop(params, 'foot_pivot_type')
        layout.prop(params, 'extra_ik_toe')
        layout.prop(params, 'make_toe_break')
        layout.prop(params, 'move_foot_spin')
        layout.prop(params, 'make_bendable_foot')


        super().parameters_ui(layout, params, 'Foot')


def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Thigh.L')
    bone.head = 0.0980, 0.0124, 1.0720
    bone.tail = 0.0980, -0.0286, 0.5372
    bone.roll = 0.0000
    bone.use_connect = False
    bones['Thigh.L'] = bone.name
    bone = arm.edit_bones.new('Shin.L')
    bone.head = 0.0980, -0.0286, 0.5372
    bone.tail = 0.0980, 0.0162, 0.0852
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Thigh.L']]
    bones['Shin.L'] = bone.name
    bone = arm.edit_bones.new('Foot.L')
    bone.head = 0.0980, 0.0162, 0.0852
    bone.tail = 0.0980, -0.0934, 0.0167
    bone.roll = 0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Shin.L']]
    bones['Foot.L'] = bone.name
    bone = arm.edit_bones.new('Toe.L')
    bone.head = 0.0980, -0.0934, 0.0167
    bone.tail = 0.0980, -0.1606, 0.0167
    bone.roll = -0.0000
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Foot.L']]
    bones['Toe.L'] = bone.name
    bone = arm.edit_bones.new('Heel.L')
    bone.head = 0.0600, 0.0459, 0.0000
    bone.tail = 0.1400, 0.0459, 0.0000
    bone.roll = 0.0000
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['Foot.L']]
    bones['Heel.L'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Thigh.L']]
    pbone.rigify_type = 'WayRig.limbs.leg'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Shin.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Foot.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Toe.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Heel.L']]
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
