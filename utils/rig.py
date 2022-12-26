import bpy

def rig_is_child(rig, parent, *, strict=False):
    """
    Checks if the rig is a child of the parent.
    Unless strict is True, returns true if the rig and parent are the same.
    """
    if parent is None:
        return True

    if rig and strict:
        rig = rig.rigify_parent

    while rig:
        if rig is parent:
            return True

        rig = rig.rigify_parent

    return False
