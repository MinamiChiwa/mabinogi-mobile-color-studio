"""Shared source location; test files and application files live separately."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STUDIO = ROOT / "work" / "studio"
