from typing import List
from bpy.utils import register_class, unregister_class
import importlib

rigify_info = {
    "name": "WayRig"
}

from . import ui, generate

modules = [
	ui,
    generate,
]

def register_unregister_modules(modules: List, register: bool):
	"""Recursively register or unregister modules by looking for either
	un/register() functions or lists named `registry` which should be a list of
	registerable classes.
	"""
	register_func = register_class if register else unregister_class

	for m in modules:
		if register:
			importlib.reload(m)
		if hasattr(m, 'registry'):
			for c in m.registry:
				try:
					register_func(c)
				except Exception as e:
					un = 'un' if not register else ''
					print(f"Warning: CloudRig failed to {un}register class: {c.__name__}")
					print(e)

		if hasattr(m, 'modules'):
			register_unregister_modules(m.modules, register)

		if register and hasattr(m, 'register'):
			m.register()
		elif hasattr(m, 'unregister'):
			m.unregister()



def register():
    print("Registered WayRig Feature Set")
    register_unregister_modules(modules, True)


def unregister():
    print("Unregistered WayRig Feature Set")
    register_unregister_modules(modules, False)
