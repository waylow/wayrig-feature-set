
# Wayrig
This is my experimental feature set for Rigify.

It is called '**Wayrig**' because....well I'm sure you can figure that out.

>[!WARNING]
> This feature set is currently **NOT** compatible with any of the Vanilla Rigify

Why? I have changed some hard coded names in the generator file, so if you try to combine this with a vanilla component, it will look for a name that does not exist.
For this reason, I have copied versions of all the existing component types and edited them to point towards my changed generator file.


# Changes

## Core Rigify:

- Renamed the auto generated root bone from  `root` to `Root`
  All my bones were title case - except the most important in the hierarchy haha. I wish to add this as an option on the armature rather than the hardcoded names (hacky).

- Added my own WayRig generator in the rigify menu
  This is so you can invoke the Wayrig generator rather than the default version (hacky)

- Adjusted the naming convention
  A lot of the names generate with .001 or _end
  I tweaked this but it requires that the base name has  numerals at the end.  Eg `Bone_01.L` default rigify will name that Bone_01_end.L but Wayrig will name that Bone_02.L

- hard coded wirewidth to 2.0
This just makes the widgets thicker.  This should be setting on the armature.

## Super Copy/ Raw Copy
- added relinking for 'None' (a little hacky)
  You can type `None` into the parent name and it will remove the parent.  (this is useful when using the Armature Constraint)

## Super Copy Plus (experimental):
- added basic parent switching (still WIP)
  This is still an unfished component that adds parent switching to this type.  (I wish to add parent switching to all types)

## Spine:
- exposed the b-bone segments in generation
  Set the number of b-bone segments in the spine.

- added option to position the Torso bone (Hacky)
  I found a really hacky way to decide which bone and at what distance to add the main torso control.  I think it would be better if you could place the bone pre-generation and name it as the position the control will be generated.  (if that bone doesn't exist - rigify should just create it)

- The `hips` and `chest` names are no longer hardcoded.

- Added slider property so you can enable/disable the amount of volume preservation.

## Limbs (Leg and Arm):
- Can set the name of the IK pole targets
- added a way to display the VIS bone as grey (hacky)
- changed the IK swing widget (and how it generates)
This widget setup adds 1 extra bone to be the widget override.  It means the double arrow widget does not obstruct when animating.

## Leg Component:
- added option to put the toe pivot at the end of the toe (on the floor)
- added bendable foot option (for cartoony chars)
 - updated the heel to remove the old limit rotation constraint (it uses drivers now)

## Leg Plus (experimental):
- trying to add toe break options which is still wip

## Eye:
- add a way to increase/decrease the distance the eye controls are generated
- world aligned the eyes
- [New type] Added Clamshell Eyelid Component type
- [New type] Added Basic eye (striped down version)

## Skin Anchor:
- added reparenting option

## Basic Chain/ Stretchy Chain:
- added property to enable/disable volume preservation
- changed the way the drivers are generated (bbone scale in/out)

## Jaw:
- rename generated mouth control to "Mouth_master" (hardcoded)
- rename sample bones

## Super Finger:
- averaged the bone rolls
This makes the control generate in a nicer position if the fingers are modelled with a lot of bend.

## Simple Tentacle:
- added tentacle tweaks (euler the control bones, rename sample bones)

## Tongue Rig (new):
- added tongue rig (edited skin rig)
- renamed tongue master bone

## Samples:
 - fixed anchor and glue samples (samples not correct)
 - renamed the bones (on most of them because of all the .001)
