"""Adaptateurs d'application : le cœur ne connaît que l'interface `AppAdapter`."""

from engine.adapters.accessibility import AccessibilityAdapter
from engine.adapters.base import AppAdapter, Command, Rect, TargetHint
from engine.adapters.blender import BlenderAdapter
from engine.adapters.profiles import AppProfile, load_profile
from engine.adapters.router import SensorRouter
from engine.adapters.vision import HoloAssertVerifier, VisionAdapter

# Adaptateurs de plugin branchés sur le canal TCP add-on, par identifiant d'application.
PLUGINS = {"blender": BlenderAdapter}
# Application servie par le canal add-on quand aucune leçon n'est chargée.
DEFAULT_PLUGIN_APP = {"id": "blender", "name": "Blender", "version": "", "sensor": "addon"}

__all__ = ["AccessibilityAdapter", "AppAdapter", "AppProfile", "BlenderAdapter", "Command",
           "DEFAULT_PLUGIN_APP", "HoloAssertVerifier", "PLUGINS", "Rect", "SensorRouter",
           "TargetHint", "VisionAdapter", "load_profile"]
