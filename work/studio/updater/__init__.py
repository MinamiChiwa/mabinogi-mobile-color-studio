"""User-controlled, signed updates for the portable Windows build."""

from .manifest import ManifestError, verify_manifest
from .planner import plan_update

__all__=['ManifestError','verify_manifest','plan_update']
