# SPDX-License-Identifier: GPL-2.0-or-later

import bpy
import math
import functools
import mathutils

from itertools import count
from mathutils import Vector, Matrix

from rigify.utils.naming import make_derived_name, mirror_name, change_name_side, Side, SideZ
from rigify.utils.bones import align_bone_z_axis, put_bone
from rigify.utils.widgets import (widget_generator, generate_circle_geometry,
                              generate_circle_hull_geometry)
from rigify.utils.widgets_basic import create_circle_widget
from ....utils.switch_parent import SwitchParentBuilder
from rigify.utils.misc import map_list, matrix_from_axis_pair, LazyRef

from rigify.base_rig import stage, RigComponent

from ..skin.skin_nodes import ControlBoneNode
from ..skin.skin_parents import ControlBoneParentOffset
from ..skin.skin_rigs import BaseSkinRig

from ..skin.basic_chain import Rig as BasicChainRig


class Rig(BaseSkinRig):
    """
    Eye rig that manages two child eyelid chains. The chains must
    connect at their ends using T/B symmetry.
    """

    def find_org_bones(self, bone):
        return bone.name

    cluster_control = None

    def initialize(self):
        super().initialize()

        bone = self.get_bone(self.base_bone)
        self.center = bone.head
        self.axis = bone.vector

        self.eye_corner_nodes = []
        self.eye_corner_matrix = None

        # Create the cluster control (it will assign self.cluster_control)
        if not self.cluster_control:
            self.create_cluster_control()

        self.init_child_chains()

    def create_cluster_control(self):
        return EyeClusterControl(self)

    ####################################################
    # UTILITIES
    '''
    def is_eye_control_node(self, node):
        return node.rig in self.child_chains and node.is_master_node

    def is_eye_corner_node(self, node):
        # Corners are nodes where the two T and B chains merge
        sides = set(n.name_split.side_z for n in node.get_merged_siblings())
        return {SideZ.BOTTOM, SideZ.TOP}.issubset(sides)

    def init_eye_corner_space(self):
        """Initialize the coordinate space of the eye based on two corners."""
        if self.eye_corner_matrix:
            return

        if len(self.eye_corner_nodes) != 2:
            self.raise_error('Expected 2 eye corners, but found {}', len(self.eye_corner_nodes))

        # Build a coordinate space with XY plane based on eye axis and two corners
        corner_axis = self.eye_corner_nodes[1].point - self.eye_corner_nodes[0].point

        matrix = matrix_from_axis_pair(self.axis, corner_axis, 'x').to_4x4()
        matrix.translation = self.center
        self.eye_corner_matrix = matrix.inverted()

        # Compute signed angles from space_axis to the eye corners
        amin, amax = self.eye_corner_range = list(
            sorted(map(self.get_eye_corner_angle, self.eye_corner_nodes)))

        if not (amin <= 0 <= amax):
            self.raise_error('Bad relative angles of eye corners: {}..{}',
                             math.degrees(amin), math.degrees(amax))

    def get_eye_corner_angle(self, node):
        """Compute a signed Z rotation angle from the eye axis to the node."""
        pt = self.eye_corner_matrix @ node.point
        return math.atan2(pt.x, pt.y)
    
    def get_master_control_position(self):
        """Compute suitable position for the master control."""
        self.init_eye_corner_space()

        # Place the control between the two corners on the eye axis
        pcorners = [node.point for node in self.eye_corner_nodes]

        point, _ = mathutils.geometry.intersect_line_line(
            self.center, self.center + self.axis, pcorners[0], pcorners[1]
        )
        return point
    
    def get_lid_follow_influence(self, node):
        """Compute the influence factor of the eye movement on this eyelid control node."""
        self.init_eye_corner_space()

        # Interpolate from axis to corners based on Z angle
        angle = self.get_eye_corner_angle(node)
        amin, amax = self.eye_corner_range

        if amin < angle < 0:
            return 1 - min(1, angle/amin) ** 2
        elif 0 < angle < amax:
            return 1 - min(1, angle/amax) ** 2
        else:
            return 0
    '''
    ####################################################
    # BONES
    #
    # ctrl:
    #   master:
    #     Parent control for moving the whole eye.
    #   target:
    #     Individual target this eye aims for.
    # mch:
    #   master:
    #     Bone that rotates to track ctrl.target.
    #   track:
    #     Bone that translates to follow mch.master tail.
    # deform:
    #   master:
    #     Deform mirror of ctrl.master.
    #   eye:
    #     Deform bone that rotates with mch.master.
    #   iris:
    #     Iris deform bone at master tail that scales with ctrl.target
    #
    ####################################################

    ####################################################
    # CHILD CHAINS
    
    def init_child_chains(self):
        self.child_chains = [rig for rig in self.rigify_children if isinstance(rig, BasicChainRig)]

        # Inject a component twisting handles to the eye radius
        for child in self.child_chains:
            self.patch_chain(child)

    def patch_chain(self, child):
        return EyelidChainPatch(child, self)
    '''
    ####################################################
    # CONTROL NODES

    def extend_mid_node_parent(self, parent, node):
        parent = ControlBoneParentOffset(self, node, parent)

        # Add movement of the eye to the eyelid controls
        parent.add_copy_local_location(
            LazyRef(self.bones.mch, 'track'),
            influence=LazyRef(self.get_lid_follow_influence, node)
        )

        return parent
    '''
    ####################################################
    # SCRIPT

    @stage.configure_bones
    def configure_script_panels(self):
        ctrl = self.bones.ctrl

        controls = sum((chain.get_all_controls() for chain in self.child_chains), ctrl.flatten())
        panel = self.script.panel_with_selected_check(self, controls)

        self.add_custom_properties()
        self.add_ui_sliders(panel)

    def add_custom_properties(self):
        target = self.bones.ctrl.target

        if self.params.eyelid_follow:
            self.make_property(
                target, 'lid_follow', (self.params.eyelid_follow_factor),
                description='Eylids follow eye movement'
            )

    def add_ui_sliders(self, panel, *, add_name=False):
        target = self.bones.ctrl.target

        name_tail = f' ({target})' if add_name else ''
        follow_text = f'Eyelids Follow{name_tail}'

        if self.params.eyelid_follow:
            panel.custom_prop(target, 'lid_follow', text=follow_text, slider=True)



    ####################################################
    # Master control

    @stage.generate_bones
    def make_master_control(self):
        org = self.bones.org
        name = self.copy_bone(org, make_derived_name(org, 'ctrl', '_master'), parent=True)
        self.bones.ctrl.master = name

    @stage.configure_bones
    def configure_master_control(self):
        self.copy_bone_properties(self.bones.org, self.bones.ctrl.master)

    @stage.generate_widgets
    def make_master_control_widget(self):
        ctrl = self.bones.ctrl.master
        create_circle_widget(self.obj, ctrl, radius=1, head_tail=0.25)

    ####################################################
    # Tracking MCH

    @stage.generate_bones
    def make_mch_track_bones(self):
        org = self.bones.org
        mch = self.bones.mch

        mch.master = self.copy_bone(org, make_derived_name(org, 'mch'))
        mch.track = self.copy_bone(org, make_derived_name(org, 'mch', '_track'), scale=1/4)

        put_bone(self.obj, mch.track, self.get_bone(org).tail)

    @stage.parent_bones
    def parent_mch_track_bones(self):
        mch = self.bones.mch
        ctrl = self.bones.ctrl
        self.set_bone_parent(mch.master, ctrl.master)
        self.set_bone_parent(mch.track, ctrl.master)

    @stage.rig_bones
    def rig_mch_track_bones(self):
        mch = self.bones.mch
        ctrl = self.bones.ctrl

        # Rotationally track the target bone in mch.master
        self.make_constraint(mch.master, 'DAMPED_TRACK', ctrl.target)

        # Translate to track the tail of mch.master in mch.track. Its local
        # location is then copied to the control nodes.
        # Two constraints are used to provide different X and Z influence values.
        con_z = self.make_constraint(
            mch.track, 'COPY_LOCATION', mch.master, head_tail=1, name='lid_follow',
            use_xyz=(False, False, True),
            space='CUSTOM', space_object=self.obj, space_subtarget=self.bones.org,
        )

        # Apply follow slider influence(s)
        if self.params.eyelid_follow:
            factor = self.params.eyelid_follow_factor

            self.make_driver(
                con_z, 'influence', expression=f'var*{factor}',
                variables=[(ctrl.target, 'lid_follow')]
            )

    ####################################################
    # ORG bone

    @stage.parent_bones
    def parent_org_chain(self):
        self.set_bone_parent(self.bones.org, self.bones.ctrl.master, inherit_scale='FULL')

    ####################################################
    # Deform bones

    @stage.generate_bones
    def make_deform_bone(self):
        org = self.bones.org
        deform = self.bones.deform
        deform.master = self.copy_bone(org, make_derived_name(org, 'def', '_master'), scale=3/2)

        if self.params.make_deform_eye:
            deform.eye = self.copy_bone(org, make_derived_name(org, 'def'))
            if self.params.make_deform_iris:
                deform.iris = self.copy_bone(org, make_derived_name(org, 'def', '_iris'), scale=1/2)
                put_bone(self.obj, deform.iris, self.get_bone(org).tail)

    @stage.parent_bones
    def parent_deform_chain(self):
        deform = self.bones.deform
        self.set_bone_parent(deform.master, self.bones.org)

        if self.params.make_deform_eye:
            self.set_bone_parent(deform.eye, self.bones.mch.master)
            if self.params.make_deform_iris:
                self.set_bone_parent(deform.iris, deform.eye)

    @stage.rig_bones
    def rig_deform_chain(self):
        if self.params.make_deform_iris:
            # Copy XZ local scale from the eye target control
            self.make_constraint(
                self.bones.deform.iris, 'COPY_SCALE', self.bones.ctrl.target,
                owner_space='LOCAL', target_space='LOCAL_OWNER_ORIENT', use_y=False,
            )

    ####################################################
    # SETTINGS

    @classmethod
    def add_parameters(self, params):
        params.make_deform_eye = bpy.props.BoolProperty(
            name="Deform Eye",
            default=True,
            description="Create a deform bone for the eye"
        )

        params.make_deform_iris = bpy.props.BoolProperty(
            name="Deform Iris",
            default=False,
            description="Create a deform bone for the iris"
        )

        params.eyelid_follow= bpy.props.BoolProperty(
            name="Eyelid Follow Slider",
            default=False,
            description="Create eyelid follow influence slider (otherwise it will follow with influence of 1.0)"
        )

        params.eyelid_follow_factor = bpy.props.FloatProperty(
            name="Eyelids Follow Factor",
            default= 0.7, min=0, max=1,
            description="Default factor for the Eyelids Follow slider",
        )

    @classmethod
    def parameters_ui(self, layout, params):
        col = layout.column()
        col.prop(params, "make_deform_eye", text="Eyeball Deforms")
        if params.make_deform_eye:
            col.prop(params, "make_deform_iris", text="Iris Deforms")


        col.prop(params, "eyelid_follow")
        if params.eyelid_follow:
            row = col.row(align=True)
            row.prop(params, "eyelid_follow_factor", index=0, text="Follow influence", slider=True)



class EyeClusterControl(RigComponent):
    """Component generating a common control for an eye cluster."""

    def __init__(self, owner):
        super().__init__(owner)

        self.find_cluster_rigs()

    def find_cluster_rigs(self):
        """Find and register all other eyes that belong to this cluster."""
        owner = self.owner

        owner.cluster_control = self
        self.rig_list = [owner]

        # Collect all sibling eye rigs
        parent_rig = owner.rigify_parent
        if parent_rig:
            for rig in parent_rig.rigify_children:
                if isinstance(rig, Rig) and rig != owner:
                    rig.cluster_control = self
                    self.rig_list.append(rig)

        self.rig_count = len(self.rig_list)

    ####################################################
    # UTILITIES

    def find_cluster_position(self):
        """Compute the eye cluster control position and orientation."""

        # Average location and Y axis of all the eyes
        axis = Vector((0, 0, 0))
        center = Vector((0, 0, 0))
        length = 0

        for rig in self.rig_list:
            bone = self.get_bone(rig.base_bone)
            axis += bone.y_axis
            center += bone.head
            length += bone.length

        axis /= self.rig_count
        center /= self.rig_count
        length /= self.rig_count

        # Create the matrix from the average Y and world Z
        # matrix = matrix_from_axis_pair((0, 0, 1), axis, 'z').to_4x4()
        matrix = matrix_from_axis_pair((0, 1, 0), (1,0,0), 'x').to_4x4()
        matrix.translation = center + axis * length * 5

        self.size = length * 3 / 4
        self.matrix = matrix
        self.inv_matrix = matrix.inverted()

    def project_rig_control(self, rig):
        """Intersect the given eye Y axis with the cluster plane, returns (x,y,0)."""
        bone = self.get_bone(rig.base_bone)

        head = self.inv_matrix @ bone.head
        tail = self.inv_matrix @ bone.tail
        axis = tail - head

        return head + axis * (-head.y / axis.y)

    def get_common_rig_name(self):
        """Choose a name for the cluster control based on the members."""
        names = set(rig.base_bone for rig in self.rig_list)
        name = min(names)

        if mirror_name(name) in names:
            return change_name_side(name, side=Side.MIDDLE)

        return name

    def get_rig_control_matrix(self, rig):
        """Compute a matrix for an individual eye sub-control."""
        matrix = self.matrix.copy()
        matrix.translation = self.matrix @ self.rig_points[rig]
        return matrix

    def get_master_control_layers(self):
        """Combine layers of all eyes for the cluster control."""
        all_layers = [list(self.get_bone(rig.base_bone).layers) for rig in self.rig_list]
        return [any(items) for items in zip(*all_layers)]

    def get_all_rig_control_bones(self):
        """Make a list of all control bones of all clustered eyes."""
        return list(set(sum((rig.bones.ctrl.flatten() for rig in self.rig_list), [self.master_bone])))

    ####################################################
    # STAGES

    def initialize(self):
        self.find_cluster_position()
        self.rig_points = {rig: self.project_rig_control(rig) for rig in self.rig_list}

    def generate_bones(self):
        if self.rig_count > 1:
            self.master_bone = self.make_master_control()
            self.child_bones = []

            for rig in self.rig_list:
                rig.bones.ctrl.target = child = self.make_child_control(rig)
                self.child_bones.append(child)
        else:
            self.master_bone = self.make_child_control(self.rig_list[0])
            self.child_bones = [self.master_bone]
            self.owner.bones.ctrl.target = self.master_bone

        self.build_parent_switch()

    def make_master_control(self):
        name = self.new_bone(make_derived_name(self.get_common_rig_name(), 'ctrl', 's_master')) # make it plural Hack
        bone = self.get_bone(name)
        bone.matrix = self.matrix
        bone.length = self.size
        bone.layers = self.get_master_control_layers()
        return name

    def make_child_control(self, rig):
        name = rig.copy_bone(
            rig.base_bone, make_derived_name(rig.base_bone, 'ctrl'), length=self.size)
        self.get_bone(name).matrix = self.get_rig_control_matrix(rig)
        return name

    def build_parent_switch(self):
        pbuilder = SwitchParentBuilder(self.owner.generator)

        org_parent = self.owner.rig_parent_bone
        parents = [org_parent] if org_parent else []

        pbuilder.build_child(
            self.owner, self.master_bone,
            prop_name=f'Parent ({self.master_bone})',
            extra_parents=parents, select_parent=org_parent,
            controls=self.get_all_rig_control_bones
        )

    def parent_bones(self):
        if self.rig_count > 1:
            self.get_bone(self.master_bone).use_local_location = False

            for child in self.child_bones:
                self.set_bone_parent(child, self.master_bone)

    def configure_bones(self):
        for child in self.child_bones:
            bone = self.get_bone(child)
            bone.lock_rotation = (True, True, True)
            bone.lock_rotation_w = True

        # When the cluster master control is selected, show sliders for all eyes
        if self.rig_count > 1:
            panel = self.owner.script.panel_with_selected_check(self.owner, [self.master_bone])
            # Euler Eyes Master
            master = self.get_bone(self.master_bone)
            master.rotation_mode = 'XYZ'

            for rig in self.rig_list:
                rig.add_ui_sliders(panel, add_name=True)

    def generate_widgets(self):
        for child in self.child_bones:
            create_eye_widget(self.obj, child)

        if self.rig_count > 1:
            pt2d = [p.to_2d() / self.size for p in self.rig_points.values()]
            create_eye_cluster_widget(self.obj, self.master_bone, points=pt2d)


@widget_generator
def create_eye_widget(geom, *, size=1):
    mat_rot = mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
    generate_circle_geometry(geom, Vector((0, 0, 0)), size/2 , matrix=mat_rot)


@widget_generator
def create_eye_cluster_widget(geom, *, size=1, points):
    mat_rot = mathutils.Matrix.Rotation(math.radians(90), 4, 'X')
    hpoints = [points[i] for i in mathutils.geometry.convex_hull_2d(points)]

    # generate_circle_hull_geometry(geom, hpoints, size*0.75, size*0.6,  matrix=mat_rot)
    generate_circle_hull_geometry(geom, hpoints, size   , size*0.85, matrix=mat_rot)


def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Eye.L')
    bone.head = 0.0000, 0.0000, 0.0000
    bone.tail = 0.0000, -0.0125, 0.0000
    bone.roll = 0.0000
    bone.use_connect = False
    bones['Eye.L'] = bone.name
    bone = arm.edit_bones.new('Lid_01.T.L')
    bone.head = 0.0155, -0.0006, -0.0003
    bone.tail = 0.0114, -0.0099, 0.0029
    bone.roll = 2.9453
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['Eye.L']]
    bones['Lid_01.T.L'] = bone.name
    bone = arm.edit_bones.new('Lid_01.B.L')
    bone.head = 0.0155, -0.0006, -0.0003
    bone.tail = 0.0112, -0.0095, -0.0039
    bone.roll = -0.0621
    bone.use_connect = False
    bone.parent = arm.edit_bones[bones['Eye.L']]
    bones['Lid_01.B.L'] = bone.name
    bone = arm.edit_bones.new('Lid_02.T.L')
    bone.head = 0.0114, -0.0099, 0.0029
    bone.tail = 0.0034, -0.0149, 0.0040
    bone.roll = 2.1070
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Lid_01.T.L']]
    bones['Lid_02.T.L'] = bone.name
    bone = arm.edit_bones.new('Lid_02.B.L')
    bone.head = 0.0112, -0.0095, -0.0039
    bone.tail = 0.0029, -0.0140, -0.0057
    bone.roll = 0.8337
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Lid_01.B.L']]
    bones['Lid_02.B.L'] = bone.name
    bone = arm.edit_bones.new('Lid_03.T.L')
    bone.head = 0.0034, -0.0149, 0.0040
    bone.tail = -0.0046, -0.0157, 0.0026
    bone.roll = 1.7002
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Lid_02.T.L']]
    bones['Lid_03.T.L'] = bone.name
    bone = arm.edit_bones.new('Lid_03.B.L')
    bone.head = 0.0029, -0.0140, -0.0057
    bone.tail = -0.0041, -0.0145, -0.0057
    bone.roll = 1.0671
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Lid_02.B.L']]
    bones['Lid_03.B.L'] = bone.name
    bone = arm.edit_bones.new('Lid_04.T.L')
    bone.head = -0.0046, -0.0157, 0.0026
    bone.tail = -0.0123, -0.0140, -0.0049
    bone.roll = 1.0850
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Lid_03.T.L']]
    bones['Lid_04.T.L'] = bone.name
    bone = arm.edit_bones.new('Lid_04.B.L')
    bone.head = -0.0041, -0.0145, -0.0057
    bone.tail = -0.0123, -0.0140, -0.0049
    bone.roll = 1.1667
    bone.use_connect = True
    bone.parent = arm.edit_bones[bones['Lid_03.B.L']]
    bones['Lid_04.B.L'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Eye.L']]
    pbone.rigify_type = 'WayRig.face.skin_eye'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Lid_01.T.L']]
    pbone.rigify_type = 'WayRig.skin.stretchy_chain'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    try:
        pbone.rigify_parameters.skin_chain_pivot_pos = 2
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.bbones = 5
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.skin_chain_connect_mirror = [False, False]
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['Lid_01.B.L']]
    pbone.rigify_type = 'WayRig.skin.stretchy_chain'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    try:
        pbone.rigify_parameters.skin_chain_pivot_pos = 2
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.bbones = 5
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.skin_chain_connect_mirror = [False, False]
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['Lid_02.T.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Lid_02.B.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Lid_03.T.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Lid_03.B.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Lid_04.T.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    pbone = obj.pose.bones[bones['Lid_04.B.L']]
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
